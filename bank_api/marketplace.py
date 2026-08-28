from __future__ import annotations

import json
import os
import re
import secrets
from typing import Callable
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field


REQUEST_STATUSES = {
    "submitted",
    "providers_notified",
    "provider_interested",
    "selected",
    "cancelled",
}
MATCH_STATUSES = {"matched", "notified", "interested", "not_available", "selected"}


class PatientRequestCreate(BaseModel):
    province: str = Field(min_length=2, max_length=80)
    city: str = Field(min_length=2, max_length=80)
    location_text: str = Field(default="", max_length=160)
    service: str = Field(min_length=2, max_length=180)
    insurer: str = Field(default="", max_length=120)
    preferred_time: str = Field(default="", max_length=160)
    budget_min: int | None = Field(default=None, ge=0)
    budget_max: int | None = Field(default=None, ge=0)
    contact: str = Field(default="", max_length=80)
    is_test: bool = False


class RequestSubmit(BaseModel):
    public_token: str = Field(min_length=16, max_length=200)
    provider_ids: list[UUID] = Field(min_length=1, max_length=5)


class ProviderResponse(BaseModel):
    access_token: str = Field(min_length=16, max_length=200)
    match_id: UUID
    decision: str
    estimated_price_min: int | None = Field(default=None, ge=0)
    estimated_price_max: int | None = Field(default=None, ge=0)
    earliest_available: str = Field(default="", max_length=160)
    note: str = Field(default="", max_length=700)


class PatientSelection(BaseModel):
    public_token: str = Field(min_length=16, max_length=200)
    match_id: UUID


def install_marketplace(
    app: FastAPI,
    db: Callable,
    norm: Callable[[str], str],
    brand_name: str,
    domain: str,
) -> None:
    """Install additive marketplace routes on the existing provider-bank API."""

    clean_re = re.compile(r"[\x00-\x1f]+")

    def clean(value, limit: int = 500) -> str:
        value = clean_re.sub(" ", str(value or ""))
        return re.sub(r"\s+", " ", value).strip()[:limit]

    def request_token() -> str:
        return secrets.token_urlsafe(32)

    def provider_token() -> str:
        return secrets.token_urlsafe(24)

    def event(conn, event_type: str, aggregate_type: str, aggregate_id, payload: dict) -> None:
        conn.execute(
            """
            INSERT INTO marketplace_events(event_type,aggregate_type,aggregate_id,payload)
            VALUES(%s,%s,%s,%s::jsonb)
            """,
            (event_type, aggregate_type, aggregate_id, json.dumps(payload, ensure_ascii=False)),
        )

    def require_request(conn, request_id: UUID, token: str):
        row = conn.execute(
            "SELECT * FROM marketplace_requests WHERE id=%s AND public_token=%s",
            (request_id, clean(token, 200)),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="request_not_found")
        return row

    def provider_access(conn, provider_id):
        row = conn.execute(
            "SELECT access_token FROM marketplace_provider_access WHERE provider_id=%s AND active",
            (provider_id,),
        ).fetchone()
        if row:
            return row["access_token"]
        token = provider_token()
        conn.execute(
            """
            INSERT INTO marketplace_provider_access(provider_id,access_token)
            VALUES(%s,%s)
            ON CONFLICT(provider_id) DO NOTHING
            """,
            (provider_id, token),
        )
        row = conn.execute(
            "SELECT access_token FROM marketplace_provider_access WHERE provider_id=%s",
            (provider_id,),
        ).fetchone()
        return row["access_token"]

    def match_candidates(conn, body: PatientRequestCreate, limit: int = 12):
        service = norm(body.service)
        like_service = f"%{service}%"
        params: list = [body.province, body.city, service, like_service, service]
        insurance_clause = ""
        if clean(body.insurer, 120):
            insurance_clause = """
              AND EXISTS (
                SELECT 1
                FROM bank_contracts bc
                JOIN bank_insurers bi ON bi.id=bc.insurer_id
                WHERE bc.provider_id=p.id AND bc.location_id=l.id
                  AND bc.status='active' AND bi.name=%s
              )
            """
            params.append(clean(body.insurer, 120))
        params.append(limit)
        return conn.execute(
            f"""
            SELECT DISTINCT ON (p.id)
              p.id AS provider_id,p.name,p.provider_type,
              l.id AS location_id,l.province,l.city,l.district,l.address,
              ps.confidence,
              src.name AS source_name,src.url AS source_url,src.source_type,
              src.last_checked_at,
              COALESCE((
                SELECT jsonb_agg(DISTINCT bi.name)
                FROM bank_contracts bc
                JOIN bank_insurers bi ON bi.id=bc.insurer_id
                WHERE bc.provider_id=p.id AND bc.location_id=l.id AND bc.status='active'
              ), '[]'::jsonb) AS insurers,
              (45 + 25
                + CASE WHEN %s <> '' THEN 20 ELSE 10 END
                + CASE WHEN ps.confidence='official' OR src.source_type='official' THEN 10 ELSE 5 END
              )::int AS score
            FROM bank_providers p
            JOIN bank_provider_locations pl ON pl.provider_id=p.id
            JOIN bank_locations l ON l.id=pl.location_id
            JOIN bank_provider_services ps ON ps.provider_id=p.id
            JOIN bank_services s ON s.id=ps.service_id
            LEFT JOIN bank_sources src ON src.id=ps.source_id
            WHERE p.active=TRUE
              AND l.province=%s
              AND l.city=%s
              AND (
                s.normalized_name=%s
                OR s.normalized_name LIKE %s
                OR %s LIKE ('%%' || s.normalized_name || '%%')
                OR EXISTS (
                  SELECT 1 FROM bank_service_aliases sa
                  WHERE sa.service_id=s.id
                    AND (sa.normalized_alias=%s OR sa.normalized_alias LIKE %s)
                )
              )
              {insurance_clause}
            ORDER BY p.id,
              CASE WHEN ps.confidence='official' OR src.source_type='official' THEN 1 ELSE 0 END DESC,
              src.authority_rank DESC NULLS LAST
            LIMIT %s
            """,
            [clean(body.insurer, 120), *params[:5], service, like_service, *params[5:]],
        ).fetchall()

    def public_match(row, include_offer: bool = False, include_contact: bool = False) -> dict:
        data = {
            "match_id": str(row["match_id"] if "match_id" in row else row["id"]),
            "provider_id": str(row["provider_id"]),
            "provider_name": row["name"],
            "provider_type": row["provider_type"],
            "province": row["province"],
            "city": row["city"],
            "district": row["district"],
            "address": row["address"],
            "score": int(row["score"] or 0),
            "status": row["status"] if "status" in row else "matched",
            "insurers": list(row["insurers"] or []),
            "trust": {
                "confidence": row["confidence"] or "unverified",
                "source_name": row["source_name"] or brand_name,
                "source_url": row["source_url"] or "",
                "source_type": row["source_type"] or "bank",
                "last_checked_at": row["last_checked_at"].isoformat()
                if row["last_checked_at"]
                else None,
            },
        }
        if include_offer:
            data["offer"] = {
                "estimated_price_min": row["estimated_price_min"],
                "estimated_price_max": row["estimated_price_max"],
                "earliest_available": row["earliest_available"],
                "note": row["provider_note"],
            }
        if include_contact:
            data["contact"] = row["phone"] or ""
        return data

    def status_payload(conn, req) -> dict:
        rows = conn.execute(
            """
            SELECT m.id AS match_id,m.provider_id,m.score,m.status,
              m.estimated_price_min,m.estimated_price_max,m.earliest_available,m.provider_note,
              p.name,p.provider_type,p.phone,l.province,l.city,l.district,l.address,
              ps.confidence,src.name AS source_name,src.url AS source_url,
              src.source_type,src.last_checked_at,
              COALESCE((
                SELECT jsonb_agg(DISTINCT bi.name)
                FROM bank_contracts bc
                JOIN bank_insurers bi ON bi.id=bc.insurer_id
                WHERE bc.provider_id=p.id AND bc.location_id=l.id AND bc.status='active'
              ), '[]'::jsonb) AS insurers
            FROM marketplace_matches m
            JOIN bank_providers p ON p.id=m.provider_id
            LEFT JOIN bank_locations l ON l.id=m.location_id
            LEFT JOIN LATERAL (
              SELECT ps0.* FROM bank_provider_services ps0
              WHERE ps0.provider_id=p.id LIMIT 1
            ) ps ON TRUE
            LEFT JOIN bank_sources src ON src.id=ps.source_id
            WHERE m.request_id=%s
              AND m.status IN ('interested','selected')
            ORDER BY (m.status='selected') DESC,m.score DESC,m.updated_at
            """,
            (req["id"],),
        ).fetchall()
        selected_id = str(req["selected_match_id"]) if req["selected_match_id"] else ""
        offers = [
            public_match(
                row,
                include_offer=True,
                include_contact=str(row["match_id"]) == selected_id,
            )
            for row in rows
        ]
        counts = conn.execute(
            """
            SELECT
              count(*) FILTER (WHERE status='notified') AS notified,
              count(*) FILTER (WHERE status='interested') AS interested,
              count(*) FILTER (WHERE status='not_available') AS unavailable,
              count(*) FILTER (WHERE status='selected') AS selected
            FROM marketplace_matches WHERE request_id=%s
            """,
            (req["id"],),
        ).fetchone()
        return {
            "request": {
                "id": str(req["id"]),
                "status": req["status"],
                "province": req["province"],
                "city": req["city"],
                "location_text": req["location_text"],
                "service": req["service_text"],
                "insurer": req["insurer"],
                "preferred_time": req["preferred_time"],
                "budget_min": req["budget_min"],
                "budget_max": req["budget_max"],
                "selected_match_id": selected_id or None,
                "created_at": req["created_at"].isoformat(),
            },
            "counts": {key: int(counts[key] or 0) for key in counts.keys()},
            "offers": offers,
        }

    @app.get("/marketplace/health")
    def marketplace_health():
        with db() as conn:
            counts = conn.execute(
                """
                SELECT
                  (SELECT count(*) FROM marketplace_requests) AS requests,
                  (SELECT count(*) FROM marketplace_matches) AS matches
                """
            ).fetchone()
        return {
            "ok": True,
            "service": "marketplace-mvp",
            "brand_name": brand_name,
            "domain": domain,
            "counts": counts,
        }

    @app.post("/marketplace/requests", status_code=201)
    def create_request(body: PatientRequestCreate):
        if body.budget_min is not None and body.budget_max is not None:
            if body.budget_min > body.budget_max:
                raise HTTPException(status_code=422, detail="budget_min_exceeds_max")
        token = request_token()
        with db() as conn:
            row = conn.execute(
                """
                INSERT INTO marketplace_requests(
                  public_token,province,city,location_text,service_text,normalized_service,
                  insurer,preferred_time,budget_min,budget_max,contact,is_test
                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    token,
                    clean(body.province, 80),
                    clean(body.city, 80),
                    clean(body.location_text, 160),
                    clean(body.service, 180),
                    norm(body.service),
                    clean(body.insurer, 120),
                    clean(body.preferred_time, 160),
                    body.budget_min,
                    body.budget_max,
                    clean(body.contact, 80),
                    body.is_test,
                ),
            ).fetchone()
            candidates = match_candidates(conn, body)
            matches = []
            for candidate in candidates:
                match = conn.execute(
                    """
                    INSERT INTO marketplace_matches(request_id,provider_id,location_id,score)
                    VALUES(%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (row["id"], candidate["provider_id"], candidate["location_id"], candidate["score"]),
                ).fetchone()
                item = dict(candidate)
                item["id"] = match["id"]
                matches.append(public_match(item))
            event(
                conn,
                "request.created",
                "request",
                row["id"],
                {
                    "request_id": str(row["id"]),
                    "city": row["city"],
                    "service": row["service_text"],
                    "match_count": len(matches),
                },
            )
            conn.commit()
        return {
            "request_id": str(row["id"]),
            "public_token": token,
            "status": row["status"],
            "matches": matches,
        }

    @app.post("/marketplace/requests/{request_id}/submit")
    def submit_request(request_id: UUID, body: RequestSubmit):
        provider_ids = list(dict.fromkeys(body.provider_ids))
        with db() as conn:
            req = require_request(conn, request_id, body.public_token)
            rows = conn.execute(
                """
                SELECT m.id,m.provider_id,p.name
                FROM marketplace_matches m
                JOIN bank_providers p ON p.id=m.provider_id
                WHERE m.request_id=%s AND m.provider_id=ANY(%s) AND m.status='matched'
                """,
                (request_id, provider_ids),
            ).fetchall()
            if len(rows) != len(provider_ids):
                raise HTTPException(status_code=409, detail="invalid_or_already_submitted_match")
            for row in rows:
                access_token = provider_access(conn, row["provider_id"])
                conn.execute(
                    "UPDATE marketplace_matches SET status='notified',updated_at=now() WHERE id=%s",
                    (row["id"],),
                )
                event(
                    conn,
                    "provider.notification.requested",
                    "match",
                    row["id"],
                    {
                        "request_id": str(request_id),
                        "provider_id": str(row["provider_id"]),
                        "provider_name": row["name"],
                        "provider_access_token": access_token,
                    },
                )
            conn.execute(
                "UPDATE marketplace_requests SET status='providers_notified',updated_at=now() WHERE id=%s",
                (request_id,),
            )
            event(
                conn,
                "request.providers_notified",
                "request",
                request_id,
                {"provider_ids": [str(x) for x in provider_ids]},
            )
            conn.commit()
        return {"ok": True, "status": "providers_notified", "notified": len(rows)}

    @app.get("/marketplace/requests/{request_id}")
    def request_status(request_id: UUID, token: str = Query(min_length=16, max_length=200)):
        with db() as conn:
            req = require_request(conn, request_id, token)
            return status_payload(conn, req)

    @app.post("/marketplace/requests/{request_id}/select")
    def select_provider(request_id: UUID, body: PatientSelection):
        with db() as conn:
            req = require_request(conn, request_id, body.public_token)
            match = conn.execute(
                """
                SELECT m.id,m.provider_id,p.name,p.phone
                FROM marketplace_matches m
                JOIN bank_providers p ON p.id=m.provider_id
                WHERE m.id=%s AND m.request_id=%s AND m.status='interested'
                """,
                (body.match_id, request_id),
            ).fetchone()
            if not match:
                raise HTTPException(status_code=409, detail="provider_offer_not_selectable")
            conn.execute(
                "UPDATE marketplace_matches SET status='selected',updated_at=now() WHERE id=%s",
                (body.match_id,),
            )
            conn.execute(
                """
                UPDATE marketplace_requests
                SET status='selected',selected_match_id=%s,updated_at=now()
                WHERE id=%s
                """,
                (body.match_id, request_id),
            )
            event(
                conn,
                "request.provider_selected",
                "request",
                request_id,
                {
                    "match_id": str(body.match_id),
                    "provider_id": str(match["provider_id"]),
                    "provider_name": match["name"],
                },
            )
            conn.commit()
        return {
            "ok": True,
            "status": "selected",
            "provider": {"name": match["name"], "contact": match["phone"] or ""},
        }

    @app.get("/marketplace/provider/dashboard")
    def provider_dashboard(access_token: str = Query(min_length=16, max_length=200)):
        with db() as conn:
            provider = conn.execute(
                """
                SELECT p.id,p.name,p.provider_type
                FROM marketplace_provider_access a
                JOIN bank_providers p ON p.id=a.provider_id
                WHERE a.access_token=%s AND a.active AND p.active
                """,
                (clean(access_token, 200),),
            ).fetchone()
            if not provider:
                raise HTTPException(status_code=404, detail="provider_access_not_found")
            rows = conn.execute(
                """
                SELECT m.id AS match_id,m.status,m.estimated_price_min,m.estimated_price_max,
                  m.earliest_available,m.provider_note,
                  r.id AS request_id,r.status AS request_status,r.city,r.province,r.location_text,
                  r.service_text,r.insurer,r.preferred_time,r.budget_min,r.budget_max,
                  CASE WHEN r.selected_match_id=m.id THEN r.contact ELSE '' END AS patient_contact,
                  r.created_at
                FROM marketplace_matches m
                JOIN marketplace_requests r ON r.id=m.request_id
                WHERE m.provider_id=%s AND m.status<>'matched'
                ORDER BY r.created_at DESC
                LIMIT 100
                """,
                (provider["id"],),
            ).fetchall()
        return {
            "provider": {
                "id": str(provider["id"]),
                "name": provider["name"],
                "type": provider["provider_type"],
            },
            "requests": [
                {
                    **{key: row[key] for key in row.keys() if key not in {"request_id", "match_id", "created_at"}},
                    "request_id": str(row["request_id"]),
                    "match_id": str(row["match_id"]),
                    "created_at": row["created_at"].isoformat(),
                }
                for row in rows
            ],
        }

    @app.post("/marketplace/provider/respond")
    def provider_respond(body: ProviderResponse):
        if body.decision not in {"interested", "not_available"}:
            raise HTTPException(status_code=422, detail="invalid_provider_decision")
        if (
            body.estimated_price_min is not None
            and body.estimated_price_max is not None
            and body.estimated_price_min > body.estimated_price_max
        ):
            raise HTTPException(status_code=422, detail="price_min_exceeds_max")
        with db() as conn:
            match = conn.execute(
                """
                SELECT m.id,m.request_id,m.provider_id,m.status
                FROM marketplace_matches m
                JOIN marketplace_provider_access a ON a.provider_id=m.provider_id
                WHERE m.id=%s AND a.access_token=%s AND a.active
                """,
                (body.match_id, clean(body.access_token, 200)),
            ).fetchone()
            if not match:
                raise HTTPException(status_code=404, detail="provider_match_not_found")
            if match["status"] not in {"notified", "interested", "not_available"}:
                raise HTTPException(status_code=409, detail="provider_match_not_respondable")
            conn.execute(
                """
                UPDATE marketplace_matches
                SET status=%s,estimated_price_min=%s,estimated_price_max=%s,
                    earliest_available=%s,provider_note=%s,updated_at=now()
                WHERE id=%s
                """,
                (
                    body.decision,
                    body.estimated_price_min if body.decision == "interested" else None,
                    body.estimated_price_max if body.decision == "interested" else None,
                    clean(body.earliest_available, 160) if body.decision == "interested" else "",
                    clean(body.note, 700) if body.decision == "interested" else "",
                    body.match_id,
                ),
            )
            if body.decision == "interested":
                conn.execute(
                    """
                    UPDATE marketplace_requests SET status='provider_interested',updated_at=now()
                    WHERE id=%s AND status<>'selected'
                    """,
                    (match["request_id"],),
                )
            event(
                conn,
                f"provider.{body.decision}",
                "match",
                body.match_id,
                {
                    "request_id": str(match["request_id"]),
                    "provider_id": str(match["provider_id"]),
                    "decision": body.decision,
                },
            )
            event(
                conn,
                "patient.notification.requested",
                "request",
                match["request_id"],
                {"reason": f"provider_{body.decision}", "match_id": str(body.match_id)},
            )
            conn.commit()
        return {"ok": True, "status": body.decision}

    def automation_guard(x_automation_token: str | None):
        configured = os.environ.get("DRLINQ_AUTOMATION_TOKEN", "")
        if not configured:
            raise HTTPException(status_code=503, detail="automation_token_not_configured")
        if not x_automation_token or not secrets.compare_digest(configured, x_automation_token):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/marketplace/automation/events")
    def automation_events(
        limit: int = Query(50, ge=1, le=200),
        x_automation_token: str | None = Header(default=None),
    ):
        automation_guard(x_automation_token)
        with db() as conn:
            rows = conn.execute(
                """
                SELECT id,event_type,aggregate_type,aggregate_id,payload,created_at
                FROM marketplace_events
                WHERE status='pending'
                ORDER BY id
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return {
            "items": [
                {
                    **dict(row),
                    "aggregate_id": str(row["aggregate_id"]),
                    "created_at": row["created_at"].isoformat(),
                }
                for row in rows
            ]
        }

    @app.post("/marketplace/automation/events/{event_id}/processed")
    def automation_event_processed(
        event_id: int,
        x_automation_token: str | None = Header(default=None),
    ):
        automation_guard(x_automation_token)
        with db() as conn:
            result = conn.execute(
                """
                UPDATE marketplace_events
                SET status='processed',processed_at=now()
                WHERE id=%s AND status='pending'
                RETURNING id
                """,
                (event_id,),
            ).fetchone()
            conn.commit()
        if not result:
            raise HTTPException(status_code=404, detail="pending_event_not_found")
        return {"ok": True, "event_id": event_id}
