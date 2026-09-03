"""Persistent Implant Intake API for the isolated DrLinq test environment."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from starlette.datastructures import UploadFile


APP_VERSION = "1.0.0-test"
MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024
FILE_SLOTS = ("opg", "cbct", "front", "upper", "lower", "right", "left")
RADIOGRAPH_SLOTS = {"opg", "cbct"}
REVIEW_STATUSES = {
    "unreviewed",
    "needs_more_info",
    "ready_for_consult",
    "needs_visit_cbct",
    "reviewed",
}
UPLOAD_ROOT = Path(os.environ.get("IMPLANT_UPLOAD_ROOT", "/data/uploads"))
SCHEMA_PATH = Path(__file__).with_name("implant_schema.sql")

app = FastAPI(title="DrLinq Implant Intake", version=APP_VERSION)


def dsn() -> str:
    return " ".join(
        [
            f"host={os.environ.get('DB_HOST', 'postgres')}",
            f"port={os.environ.get('DB_PORT', '5432')}",
            f"dbname={os.environ['DB_NAME']}",
            f"user={os.environ['DB_USER']}",
            f"password={os.environ['DB_PASSWORD']}",
            "options='-c statement_timeout=15000 -c idle_in_transaction_session_timeout=15000'",
        ]
    )


@contextmanager
def db():
    with psycopg.connect(dsn(), row_factory=dict_row) as conn:
        yield conn


@app.on_event("startup")
def startup() -> None:
    session_secret = os.environ.get("DOCTOR_SESSION_SECRET", "")
    code_hash = os.environ.get("DOCTOR_LOGIN_CODE_HASH", "")
    if len(session_secret) < 32 or not re.fullmatch(r"[0-9a-f]{64}", code_hash):
        raise RuntimeError("Doctor authentication is not configured")
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with db() as conn:
        conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()


@app.middleware("http")
async def private_response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def text_field(payload: dict[str, Any], key: str, *, required: bool = False, limit: int = 2000) -> str:
    value = payload.get(key, "")
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail=f"invalid_{key}")
    value = value.strip()
    if required and not value:
        raise HTTPException(status_code=422, detail=f"missing_{key}")
    if len(value) > limit:
        raise HTTPException(status_code=422, detail=f"{key}_too_long")
    return value


def list_field(payload: dict[str, Any], key: str, *, limit: int) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or len(value) > limit:
        raise HTTPException(status_code=422, detail=f"invalid_{key}")
    result: list[str] = []
    for item in value:
        if not isinstance(item, (str, int)) or len(str(item)) > 200:
            raise HTTPException(status_code=422, detail=f"invalid_{key}")
        result.append(str(item))
    return result


def object_field(payload: dict[str, Any], key: str, *, limit: int = 30) -> dict[str, Any]:
    value = payload.get(key, {})
    if not isinstance(value, dict) or len(value) > limit:
        raise HTTPException(status_code=422, detail=f"invalid_{key}")
    return value


def normalize_mobile(value: str) -> str:
    translation = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    normalized = value.translate(translation)
    normalized = re.sub(r"[\s()-]", "", normalized)
    if normalized.startswith("+"):
        digits = normalized[1:]
    else:
        digits = normalized
    if not digits.isdigit() or not 10 <= len(digits) <= 15:
        raise HTTPException(status_code=422, detail="invalid_mobile")
    return normalized


def validate_payload(raw: Any) -> dict[str, Any]:
    try:
        payload = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="invalid_payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="invalid_payload")

    submission_key = text_field(payload, "submission_key", required=True, limit=64)
    try:
        uuid.UUID(submission_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid_submission_key") from exc

    patient_name = text_field(payload, "name", required=True, limit=160)
    mobile = normalize_mobile(text_field(payload, "mobile", required=True, limit=40))
    city = text_field(payload, "city", required=True, limit=120)
    problem = text_field(payload, "problem", required=True, limit=500)
    jaws = list_field(payload, "jaws", limit=2)
    if not jaws or any(jaw not in {"upper", "lower"} for jaw in jaws):
        raise HTTPException(status_code=422, detail="invalid_jaws")
    teeth = list_field(payload, "teeth", limit=32)
    if any(not tooth.isdigit() or int(tooth) < 11 or int(tooth) > 48 for tooth in teeth):
        raise HTTPException(status_code=422, detail="invalid_teeth")
    jaw_parts = object_field(payload, "jawParts", limit=2)
    medical = object_field(payload, "medical", limit=20)
    if any(not isinstance(value, bool) for value in medical.values()):
        raise HTTPException(status_code=422, detail="invalid_medical")
    consent = payload.get("consent") is True
    if not consent:
        raise HTTPException(status_code=422, detail="consent_required")

    return {
        "submission_key": submission_key,
        "patient_name": patient_name,
        "mobile": mobile,
        "city": city,
        "problem": problem,
        "missing_count": text_field(payload, "missingCount", limit=80),
        "jaws": jaws,
        "jaw_parts": jaw_parts,
        "teeth": teeth,
        "medical": medical,
        "disease_text": text_field(payload, "diseaseText", limit=3000),
        "medication_text": text_field(payload, "medText", limit=3000),
        "suggested_questions": list_field(payload, "suggestedQuestions", limit=2),
        "patient_question": text_field(payload, "question", limit=3000),
        "radiograph_status": object_field(payload, "records", limit=2),
        "photo_status": object_field(payload, "photos", limit=5),
        "consent": consent,
    }


def detect_file_type(data: bytes, slot: str) -> tuple[str, str]:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if slot in RADIOGRAPH_SLOTS and data.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    raise HTTPException(status_code=415, detail=f"unsupported_file_type:{slot}")


async def read_uploads(form: Any) -> dict[str, dict[str, Any]]:
    uploads: dict[str, dict[str, Any]] = {}
    total = 0
    for slot in FILE_SLOTS:
        upload = form.get(slot)
        if upload is None or not isinstance(upload, UploadFile) or not upload.filename:
            continue
        data = await upload.read(MAX_FILE_BYTES + 1)
        await upload.close()
        if not data:
            raise HTTPException(status_code=422, detail=f"empty_file:{slot}")
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail=f"file_too_large:{slot}")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="total_upload_too_large")
        media_type, extension = detect_file_type(data, slot)
        uploads[slot] = {
            "data": data,
            "media_type": media_type,
            "extension": extension,
            "original_name": Path(upload.filename).name[:160] or f"{slot}{extension}",
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return uploads


def generate_case_code() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"IMP-{stamp}-{secrets.token_hex(3).upper()}"


@app.get("/health")
def health():
    with db() as conn:
        row = conn.execute("SELECT 1 AS ok").fetchone()
    return {
        "ok": True,
        "service": "drlinq-implant-intake-test",
        "version": APP_VERSION,
        "persistent": True,
        "database_reachable": row["ok"] == 1,
    }


@app.post("/cases", status_code=status.HTTP_201_CREATED)
async def create_case(request: Request):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_TOTAL_BYTES + 2 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="request_too_large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid_content_length") from exc
    form = await request.form(
        max_files=len(FILE_SLOTS), max_fields=2, max_part_size=MAX_FILE_BYTES
    )
    payload = validate_payload(form.get("payload"))
    uploads = await read_uploads(form)

    case_uuid = uuid.uuid4()
    case_code = generate_case_code()
    created_files: list[Path] = []
    try:
        with db() as conn:
            inserted = conn.execute(
                """
                INSERT INTO implant_cases (
                  id, case_code, submission_key, patient_name, mobile, city, problem,
                  missing_count, jaws, jaw_parts, teeth, medical, disease_text,
                  medication_text, suggested_questions, patient_question,
                  radiograph_status, photo_status, consent
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s
                )
                ON CONFLICT (submission_key) DO NOTHING
                RETURNING id, case_code, created_at
                """,
                (
                    case_uuid,
                    case_code,
                    payload["submission_key"],
                    payload["patient_name"],
                    payload["mobile"],
                    payload["city"],
                    payload["problem"],
                    payload["missing_count"],
                    Jsonb(payload["jaws"]),
                    Jsonb(payload["jaw_parts"]),
                    Jsonb(payload["teeth"]),
                    Jsonb(payload["medical"]),
                    payload["disease_text"],
                    payload["medication_text"],
                    Jsonb(payload["suggested_questions"]),
                    payload["patient_question"],
                    Jsonb(payload["radiograph_status"]),
                    Jsonb(payload["photo_status"]),
                    payload["consent"],
                ),
            ).fetchone()
            if not inserted:
                existing = conn.execute(
                    "SELECT case_code, created_at FROM implant_cases WHERE submission_key=%s",
                    (payload["submission_key"],),
                ).fetchone()
                return {
                    "ok": True,
                    "created": False,
                    "case_id": existing["case_code"],
                    "created_at": existing["created_at"],
                }

            case_dir = UPLOAD_ROOT / str(case_uuid)
            case_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            for slot, upload in uploads.items():
                file_uuid = uuid.uuid4()
                storage_name = f"{case_uuid}/{file_uuid}{upload['extension']}"
                destination = UPLOAD_ROOT / storage_name
                temporary = destination.with_suffix(destination.suffix + ".part")
                temporary.write_bytes(upload["data"])
                temporary.replace(destination)
                created_files.append(destination)
                conn.execute(
                    """
                    INSERT INTO implant_case_files (
                      id, case_id, slot, original_name, media_type, size_bytes, sha256, storage_name
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_uuid,
                        case_uuid,
                        slot,
                        upload["original_name"],
                        upload["media_type"],
                        len(upload["data"]),
                        upload["sha256"],
                        storage_name,
                    ),
                )
            conn.commit()
            return {
                "ok": True,
                "created": True,
                "case_id": inserted["case_code"],
                "created_at": inserted["created_at"],
            }
    except Exception:
        for path in created_files:
            path.unlink(missing_ok=True)
        raise


class DoctorLogin(BaseModel):
    code: str


class DoctorReview(BaseModel):
    status: str
    note: str = ""


_login_attempts: dict[str, list[float]] = {}
_login_lock = Lock()


def valid_code_hashes() -> list[str]:
    values = [
        os.environ.get("DOCTOR_LOGIN_CODE_HASH", ""),
        os.environ.get("E2E_DOCTOR_LOGIN_CODE_HASH", ""),
    ]
    return [value for value in values if re.fullmatch(r"[0-9a-f]{64}", value)]


def encode_token(expires_at: int) -> str:
    payload = json.dumps(
        {"exp": expires_at, "nonce": secrets.token_hex(16)},
        separators=(",", ":"),
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(
        os.environ["DOCTOR_SESSION_SECRET"].encode(), encoded.encode(), hashlib.sha256
    ).digest()
    return f"{encoded}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def decode_token(token: str) -> dict[str, Any]:
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected = hmac.new(
            os.environ["DOCTOR_SESSION_SECRET"].encode(), encoded.encode(), hashlib.sha256
        ).digest()
        supplied = base64.urlsafe_b64decode(supplied_signature + "=" * (-len(supplied_signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if not isinstance(payload.get("exp"), int) or payload["exp"] < int(time.time()):
            raise ValueError
        return payload
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error) as exc:
        raise HTTPException(status_code=401, detail="doctor_session_invalid") from exc


def require_doctor(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="doctor_auth_required")
    return decode_token(authorization[7:].strip())


@app.post("/doctor/login")
def doctor_login(credentials: DoctorLogin, request: Request):
    client = request.client.host if request.client else "unknown"
    now = time.time()
    with _login_lock:
        recent = [stamp for stamp in _login_attempts.get(client, []) if now - stamp < 900]
        if len(recent) >= 8:
            raise HTTPException(status_code=429, detail="too_many_login_attempts")
    supplied_hash = hashlib.sha256(credentials.code.strip().encode()).hexdigest()
    if not any(hmac.compare_digest(supplied_hash, expected) for expected in valid_code_hashes()):
        with _login_lock:
            _login_attempts[client] = [*recent, now]
        raise HTTPException(status_code=401, detail="doctor_code_invalid")
    with _login_lock:
        _login_attempts.pop(client, None)
    expires_at = int(now) + 12 * 60 * 60
    return {"ok": True, "token": encode_token(expires_at), "expires_at": expires_at}


def area_summary(row: dict[str, Any]) -> str:
    labels = {"upper": "فک بالا", "lower": "فک پایین"}
    parts = []
    for jaw in row.get("jaws") or []:
        part = (row.get("jaw_parts") or {}).get(jaw, "")
        parts.append(f"{labels.get(jaw, jaw)}{f' · {part}' if part else ''}")
    teeth = row.get("teeth") or []
    if teeth:
        parts.append("دندان‌ها: " + "، ".join(teeth))
    return " | ".join(parts) or "—"


@app.get("/cases", dependencies=[Depends(require_doctor)])
def list_cases(limit: int = Query(100, ge=1, le=250), offset: int = Query(0, ge=0)):
    with db() as conn:
        rows = conn.execute(
            """
            SELECT case_code, patient_name, mobile, city, problem, missing_count,
                   jaws, jaw_parts, teeth, status, created_at, updated_at
            FROM implant_cases
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        ).fetchall()
    items = []
    for row in rows:
        item = {**row, "case_id": row["case_code"], "area": area_summary(row)}
        item.pop("case_code", None)
        items.append(item)
    return {"items": items, "limit": limit, "offset": offset}


def load_case(case_code: str) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute(
            """
            SELECT id, case_code, patient_name, mobile, city, problem, missing_count,
                   jaws, jaw_parts, teeth, medical, disease_text, medication_text,
                   suggested_questions, patient_question, radiograph_status,
                   photo_status, status, doctor_note, reviewed_at, created_at, updated_at
            FROM implant_cases
            WHERE case_code=%s
            """,
            (case_code,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="case_not_found")
        files = conn.execute(
            """
            SELECT id, slot, original_name, media_type, size_bytes, created_at
            FROM implant_case_files
            WHERE case_id=%s
            ORDER BY created_at
            """,
            (row["id"],),
        ).fetchall()
    result = {**row}
    result.pop("id", None)
    result["case_id"] = result.pop("case_code")
    result["area"] = area_summary(result)
    result["files"] = [
        {
            **file,
            "id": str(file["id"]),
            "content_path": f"/cases/{case_code}/files/{file['id']}",
        }
        for file in files
    ]
    return result


@app.get("/cases/{case_code}", dependencies=[Depends(require_doctor)])
def get_case(case_code: str):
    return load_case(case_code)


@app.patch("/cases/{case_code}/review", dependencies=[Depends(require_doctor)])
def update_review(case_code: str, review: DoctorReview):
    if review.status not in REVIEW_STATUSES:
        raise HTTPException(status_code=422, detail="invalid_review_status")
    note = review.note.strip()
    if len(note) > 10000:
        raise HTTPException(status_code=422, detail="doctor_note_too_long")
    with db() as conn:
        row = conn.execute(
            """
            UPDATE implant_cases
            SET status=%s, doctor_note=%s, reviewed_at=now(), updated_at=now()
            WHERE case_code=%s
            RETURNING case_code, status, doctor_note, reviewed_at, updated_at
            """,
            (review.status, note, case_code),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="case_not_found")
        conn.commit()
    result = {**row, "case_id": row["case_code"]}
    result.pop("case_code", None)
    return result


@app.get("/cases/{case_code}/files/{file_id}", dependencies=[Depends(require_doctor)])
def get_case_file(case_code: str, file_id: uuid.UUID):
    with db() as conn:
        row = conn.execute(
            """
            SELECT f.storage_name, f.original_name, f.media_type
            FROM implant_case_files f
            JOIN implant_cases c ON c.id=f.case_id
            WHERE c.case_code=%s AND f.id=%s
            """,
            (case_code, file_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="file_not_found")
    path = (UPLOAD_ROOT / row["storage_name"]).resolve()
    if UPLOAD_ROOT.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="file_not_found")
    return FileResponse(
        path,
        media_type=row["media_type"],
        filename=row["original_name"],
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store"},
    )
