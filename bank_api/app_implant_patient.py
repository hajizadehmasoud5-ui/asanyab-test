"""Doctor-to-patient extension for the isolated DrLinq Implant Intake API."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from typing import Any

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

import app_implant as core

app = core.app
PATIENT_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{40,128}$")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _copy_response(response: Response, body: bytes) -> Response:
    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(
        content=body,
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type,
        background=response.background,
    )


@app.middleware("http")
async def issue_patient_access_token(request: Request, call_next):
    """Attach a one-time plaintext patient token only to newly-created cases.

    Only the SHA-256 hash is persisted. Duplicate submissions never mint a second
    token or a second case.
    """

    response = await call_next(request)
    if request.method != "POST" or request.url.path != "/cases" or response.status_code != 201:
        return response

    body = b"".join([chunk async for chunk in response.body_iterator])
    try:
        payload = json.loads(body)
    except (TypeError, json.JSONDecodeError):
        return _copy_response(response, body)

    if payload.get("created") is True and payload.get("case_id"):
        token = secrets.token_urlsafe(32)
        digest = token_hash(token)
        with core.db() as conn:
            row = conn.execute(
                """
                UPDATE implant_cases
                SET patient_access_token_hash=%s, updated_at=now()
                WHERE case_code=%s AND patient_access_token_hash IS NULL
                RETURNING case_code
                """,
                (digest, payload["case_id"]),
            ).fetchone()
            conn.commit()
        payload["patient_access_token"] = token if row else None
    else:
        payload["patient_access_token"] = None

    headers = dict(response.headers)
    headers.pop("content-length", None)
    return JSONResponse(
        payload,
        status_code=response.status_code,
        headers=headers,
        background=response.background,
    )


class DoctorPatientResponse(BaseModel):
    patient_response: str = ""
    more_info_required: bool = False
    more_info_message: str = ""
    publish: bool = False


def _validate_patient_response(review: DoctorPatientResponse) -> tuple[str, str]:
    patient_response = review.patient_response.strip()
    more_info_message = review.more_info_message.strip()
    if len(patient_response) > 10000:
        raise HTTPException(status_code=422, detail="patient_response_too_long")
    if len(more_info_message) > 5000:
        raise HTTPException(status_code=422, detail="more_info_message_too_long")
    if review.more_info_required and not more_info_message:
        raise HTTPException(status_code=422, detail="more_info_message_required")
    if review.publish and not patient_response and not review.more_info_required:
        raise HTTPException(status_code=422, detail="patient_response_required")
    return patient_response, more_info_message


def _doctor_response_result(row: dict[str, Any]) -> dict[str, Any]:
    result = {**row, "case_id": row["case_code"]}
    result.pop("case_code", None)
    return result


@app.get("/cases/{case_code}/patient-response", dependencies=[Depends(core.require_doctor)])
def get_patient_response_for_doctor(case_code: str):
    with core.db() as conn:
        row = conn.execute(
            """
            SELECT case_code,
                   patient_response_draft,
                   more_info_required_draft,
                   more_info_message_draft,
                   patient_response_published,
                   more_info_required_published,
                   more_info_message_published,
                   response_published_at,
                   updated_at
            FROM implant_cases
            WHERE case_code=%s
            """,
            (case_code,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="case_not_found")
    return _doctor_response_result(row)


@app.patch("/cases/{case_code}/patient-response", dependencies=[Depends(core.require_doctor)])
def save_patient_response(case_code: str, review: DoctorPatientResponse):
    patient_response, more_info_message = _validate_patient_response(review)
    with core.db() as conn:
        row = conn.execute(
            """
            UPDATE implant_cases
            SET patient_response_draft=%s,
                more_info_required_draft=%s,
                more_info_message_draft=%s,
                patient_response_published=CASE WHEN %s THEN %s ELSE patient_response_published END,
                more_info_required_published=CASE WHEN %s THEN %s ELSE more_info_required_published END,
                more_info_message_published=CASE WHEN %s THEN %s ELSE more_info_message_published END,
                response_published_at=CASE WHEN %s THEN now() ELSE response_published_at END,
                updated_at=now()
            WHERE case_code=%s
            RETURNING case_code,
                      patient_response_draft,
                      more_info_required_draft,
                      more_info_message_draft,
                      patient_response_published,
                      more_info_required_published,
                      more_info_message_published,
                      response_published_at,
                      updated_at
            """,
            (
                patient_response,
                review.more_info_required,
                more_info_message,
                review.publish,
                patient_response,
                review.publish,
                review.more_info_required,
                review.publish,
                more_info_message,
                review.publish,
                case_code,
            ),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="case_not_found")
        conn.commit()
    return _doctor_response_result(row)


@app.get("/patient/cases/{case_code}")
def get_patient_case(case_code: str, token: str = Query(..., min_length=40, max_length=128)):
    if not PATIENT_TOKEN_RE.fullmatch(token):
        raise HTTPException(status_code=404, detail="case_not_found")
    digest = token_hash(token)
    with core.db() as conn:
        row = conn.execute(
            """
            SELECT case_code, created_at, status,
                   patient_response_published,
                   more_info_required_published,
                   more_info_message_published,
                   response_published_at
            FROM implant_cases
            WHERE case_code=%s AND patient_access_token_hash=%s
            """,
            (case_code, digest),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="case_not_found")

    published = row["response_published_at"] is not None
    return {
        "case_id": row["case_code"],
        "created_at": row["created_at"],
        "status": row["status"],
        "patient_response": row["patient_response_published"] if published else "",
        "more_info_required": bool(row["more_info_required_published"]) if published else False,
        "more_info_message": row["more_info_message_published"] if published else "",
        "response_published_at": row["response_published_at"] if published else None,
    }
