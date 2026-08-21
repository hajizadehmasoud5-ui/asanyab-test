from __future__ import annotations

import json
import re
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

VERSION = "0.1.0"


def create_drlinq_secretary_blueprint(data_root: str | Path) -> Blueprint:
    bp = Blueprint("drlinq_secretary", __name__, url_prefix="/alanoffer")
    root = Path(data_root) / "alanoffer"
    root.mkdir(parents=True, exist_ok=True)
    db = root / "alanoffer.db"

    def con():
        c = sqlite3.connect(str(db), timeout=20)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def now() -> int:
        return int(time.time() * 1000)

    def clean(v: Any, n: int = 500) -> str:
        return re.sub(r"\s+", " ", str(v or "")).strip()[:n]

    def slugify(v: Any) -> str:
        s = clean(v, 80).lower().replace("ي", "ی").replace("ك", "ک")
        s = re.sub(r"[^a-z0-9\u0600-\u06ff]+", "-", s).strip("-")
        if not s:
            s = "clinic"
        return s[:50]

    def jload(v: Any, default):
        try:
            x = json.loads(v or "")
            return x if isinstance(x, type(default)) else default
        except Exception:
            return default

    def safe_list(v: Any, limit: int = 30, item_len: int = 100):
        if not isinstance(v, list):
            return []
        out = []
        for x in v:
            x = clean(x, item_len)
            if x and x not in out:
                out.append(x)
            if len(out) >= limit:
                break
        return out

    def safe_faq(v: Any):
        if not isinstance(v, list):
            return []
        out = []
        for row in v:
            if not isinstance(row, dict):
                continue
            q = clean(row.get("q"), 180)
            a = clean(row.get("a"), 700)
            if q and a:
                out.append({"q": q, "a": a})
            if len(out) >= 30:
                break
        return out

    def init():
        with con() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS drlinq_secretary_clinics(
                    id TEXT PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    access_token TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    city TEXT NOT NULL DEFAULT '',
                    area TEXT NOT NULL DEFAULT '',
                    greeting TEXT NOT NULL DEFAULT '',
                    services_json TEXT NOT NULL DEFAULT '[]',
                    insurers_json TEXT NOT NULL DEFAULT '[]',
                    hours_text TEXT NOT NULL DEFAULT '',
                    payment_text TEXT NOT NULL DEFAULT '',
                    faq_json TEXT NOT NULL DEFAULT '[]',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_drlinq_secretary_slug
                    ON drlinq_secretary_clinics(slug, active);

                CREATE TABLE IF NOT EXISTS drlinq_secretary_inquiries(
                    id TEXT PRIMARY KEY,
                    clinic_id TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'other',
                    patient_name TEXT NOT NULL DEFAULT '',
                    patient_phone TEXT NOT NULL DEFAULT '',
                    service TEXT NOT NULL DEFAULT '',
                    insurer TEXT NOT NULL DEFAULT '',
                    preferred_time TEXT NOT NULL DEFAULT '',
                    question TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_drlinq_secretary_inquiries
                    ON drlinq_secretary_inquiries(clinic_id, status, created_at);
                """
            )

    init()

    def clinic_auth(cid: str):
        token = clean(request.args.get("token") or request.headers.get("X-Secretary-Token"), 200)
        with con() as c:
            row = c.execute(
                "SELECT * FROM drlinq_secretary_clinics WHERE id=? AND active=1",
                (clean(cid, 160),),
            ).fetchone()
        if not row or not token or not secrets.compare_digest(token, row["access_token"]):
            return None
        return row

    def public_clinic(row):
        return {
            "id": row["id"],
            "slug": row["slug"],
            "name": row["name"],
            "category": row["category"],
            "city": row["city"],
            "area": row["area"],
            "greeting": row["greeting"],
            "services": jload(row["services_json"], []),
            "insurers": jload(row["insurers_json"], []),
            "hoursText": row["hours_text"],
            "paymentText": row["payment_text"],
            "faq": jload(row["faq_json"], []),
        }

    @bp.after_request
    def cors(resp):
        origin = request.headers.get("Origin", "")
        if origin in {
            "https://drlinq.ir",
            "https://www.drlinq.ir",
            "https://hajizadehmasoud5-ui.github.io",
        }:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Secretary-Token"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @bp.route("/api/secretary/<path:_p>", methods=["OPTIONS"])
    def options(_p):
        return ("", 204)

    @bp.get("/api/secretary/health")
    def health():
        with con() as c:
            clinics = c.execute("SELECT COUNT(*) n FROM drlinq_secretary_clinics WHERE active=1").fetchone()["n"]
            inquiries = c.execute("SELECT COUNT(*) n FROM drlinq_secretary_inquiries").fetchone()["n"]
        return jsonify(ok=True, service="drlinq-smart-secretary", version=VERSION, clinics=clinics, inquiries=inquiries)

    @bp.post("/api/secretary/clinics/register")
    def register_clinic():
        b = request.get_json(silent=True) or {}
        name = clean(b.get("name"), 160)
        if not name:
            return jsonify(error="name_required"), 400
        base = slugify(b.get("slug") or name)
        slug = base
        with con() as c:
            i = 2
            while c.execute("SELECT 1 FROM drlinq_secretary_clinics WHERE slug=?", (slug,)).fetchone():
                slug = f"{base[:42]}-{i}"
                i += 1
            cid = f"sec_{int(time.time()*1000)}_{secrets.token_hex(6)}"
            token = secrets.token_urlsafe(24)
            ts = now()
            c.execute(
                """
                INSERT INTO drlinq_secretary_clinics(
                    id,slug,access_token,name,category,city,area,greeting,
                    services_json,insurers_json,hours_text,payment_text,faq_json,
                    active,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    cid,
                    slug,
                    token,
                    name,
                    clean(b.get("category"), 100),
                    clean(b.get("city"), 80),
                    clean(b.get("area"), 120),
                    clean(b.get("greeting"), 300) or "سلام، چطور می‌توانم برای مراجعه به این مرکز کمکتان کنم؟",
                    json.dumps(safe_list(b.get("services")), ensure_ascii=False),
                    json.dumps(safe_list(b.get("insurers")), ensure_ascii=False),
                    clean(b.get("hoursText"), 300),
                    clean(b.get("paymentText"), 300),
                    json.dumps(safe_faq(b.get("faq")), ensure_ascii=False),
                    1,
                    ts,
                    ts,
                ),
            )
        return jsonify(ok=True, clinicId=cid, accessToken=token, slug=slug)

    @bp.get("/api/secretary/c/<slug>")
    def get_public_clinic(slug):
        with con() as c:
            row = c.execute(
                "SELECT * FROM drlinq_secretary_clinics WHERE slug=? AND active=1",
                (clean(slug, 80),),
            ).fetchone()
        if not row:
            return jsonify(error="not_found"), 404
        return jsonify(ok=True, clinic=public_clinic(row))

    @bp.post("/api/secretary/c/<slug>/inquiries")
    def create_inquiry(slug):
        with con() as c:
            clinic = c.execute(
                "SELECT id FROM drlinq_secretary_clinics WHERE slug=? AND active=1",
                (clean(slug, 80),),
            ).fetchone()
            if not clinic:
                return jsonify(error="not_found"), 404
            b = request.get_json(silent=True) or {}
            kind = clean(b.get("kind"), 40) or "other"
            if kind not in {"appointment", "insurance", "payment", "services", "question", "other"}:
                kind = "other"
            question = clean(b.get("question"), 1000)
            phone = clean(b.get("patientPhone"), 40)
            if not question and kind in {"question", "other"}:
                return jsonify(error="question_required"), 400
            iid = f"inq_{int(time.time()*1000)}_{secrets.token_hex(6)}"
            ts = now()
            c.execute(
                """
                INSERT INTO drlinq_secretary_inquiries(
                    id,clinic_id,kind,patient_name,patient_phone,service,insurer,
                    preferred_time,question,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    iid,
                    clinic["id"],
                    kind,
                    clean(b.get("patientName"), 100),
                    phone,
                    clean(b.get("service"), 120),
                    clean(b.get("insurer"), 120),
                    clean(b.get("preferredTime"), 160),
                    question,
                    "new",
                    ts,
                    ts,
                ),
            )
        return jsonify(ok=True, inquiryId=iid, message="درخواست شما برای مرکز ثبت شد.")

    @bp.get("/api/secretary/clinics/<cid>/dashboard")
    def clinic_dashboard(cid):
        clinic = clinic_auth(cid)
        if not clinic:
            return jsonify(error="unauthorized"), 401
        with con() as c:
            rows = c.execute(
                """
                SELECT * FROM drlinq_secretary_inquiries
                WHERE clinic_id=? ORDER BY created_at DESC LIMIT 100
                """,
                (clinic["id"],),
            ).fetchall()
        return jsonify(
            ok=True,
            clinic=public_clinic(clinic),
            inquiries=[
                {
                    "id": x["id"],
                    "kind": x["kind"],
                    "patientName": x["patient_name"],
                    "patientPhone": x["patient_phone"],
                    "service": x["service"],
                    "insurer": x["insurer"],
                    "preferredTime": x["preferred_time"],
                    "question": x["question"],
                    "status": x["status"],
                    "createdAt": x["created_at"],
                }
                for x in rows
            ],
        )

    @bp.post("/api/secretary/clinics/<cid>/profile")
    def update_profile(cid):
        clinic = clinic_auth(cid)
        if not clinic:
            return jsonify(error="unauthorized"), 401
        b = request.get_json(silent=True) or {}
        fields = {
            "name": clean(b.get("name"), 160) or clinic["name"],
            "category": clean(b.get("category"), 100),
            "city": clean(b.get("city"), 80),
            "area": clean(b.get("area"), 120),
            "greeting": clean(b.get("greeting"), 300),
            "services_json": json.dumps(safe_list(b.get("services")), ensure_ascii=False),
            "insurers_json": json.dumps(safe_list(b.get("insurers")), ensure_ascii=False),
            "hours_text": clean(b.get("hoursText"), 300),
            "payment_text": clean(b.get("paymentText"), 300),
            "faq_json": json.dumps(safe_faq(b.get("faq")), ensure_ascii=False),
        }
        with con() as c:
            c.execute(
                """
                UPDATE drlinq_secretary_clinics SET
                    name=?,category=?,city=?,area=?,greeting=?,services_json=?,insurers_json=?,
                    hours_text=?,payment_text=?,faq_json=?,updated_at=?
                WHERE id=?
                """,
                (
                    fields["name"], fields["category"], fields["city"], fields["area"],
                    fields["greeting"], fields["services_json"], fields["insurers_json"],
                    fields["hours_text"], fields["payment_text"], fields["faq_json"], now(), clinic["id"],
                ),
            )
        return jsonify(ok=True)

    @bp.post("/api/secretary/clinics/<cid>/inquiries/<iid>/status")
    def update_inquiry_status(cid, iid):
        clinic = clinic_auth(cid)
        if not clinic:
            return jsonify(error="unauthorized"), 401
        b = request.get_json(silent=True) or {}
        status = clean(b.get("status"), 30)
        if status not in {"new", "seen", "done"}:
            return jsonify(error="invalid_status"), 400
        with con() as c:
            cur = c.execute(
                "UPDATE drlinq_secretary_inquiries SET status=?,updated_at=? WHERE id=? AND clinic_id=?",
                (status, now(), clean(iid, 180), clinic["id"]),
            )
            if cur.rowcount == 0:
                return jsonify(error="not_found"), 404
        return jsonify(ok=True, status=status)

    return bp
