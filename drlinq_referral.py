from __future__ import annotations

import json
import re
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request, send_file

VERSION = "0.1.0"
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "pdf", "dcm"}
MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_FILES = 4


def create_drlinq_referral_blueprint(data_root: str | Path) -> Blueprint:
    bp = Blueprint("drlinq_referral", __name__, url_prefix="/alanoffer")
    root = Path(data_root) / "alanoffer"
    upload_root = root / "referral_files"
    upload_root.mkdir(parents=True, exist_ok=True)
    db = root / "alanoffer.db"

    def con():
        c = sqlite3.connect(str(db), timeout=20)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def now() -> int:
        return int(time.time() * 1000)

    def clean(v: Any, n: int = 1000) -> str:
        return re.sub(r"\s+", " ", str(v or "")).strip()[:n]

    def slugify(v: Any) -> str:
        s = clean(v, 80).lower().replace("ي", "ی").replace("ك", "ک")
        s = re.sub(r"[^a-z0-9\u0600-\u06ff]+", "-", s).strip("-")
        return (s or "specialist")[:48]

    def load_json(v: Any, default):
        try:
            x = json.loads(v or "")
            return x if isinstance(x, type(default)) else default
        except Exception:
            return default

    def init():
        with con() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS drlinq_referral_specialists(
                    id TEXT PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    access_token TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    clinic_name TEXT NOT NULL DEFAULT '',
                    specialty TEXT NOT NULL DEFAULT 'endodontics',
                    city TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_drlinq_referral_specialist_slug
                    ON drlinq_referral_specialists(slug, active);

                CREATE TABLE IF NOT EXISTS drlinq_referrals(
                    id TEXT PRIMARY KEY,
                    specialist_id TEXT NOT NULL,
                    patient_name TEXT NOT NULL DEFAULT '',
                    patient_phone TEXT NOT NULL DEFAULT '',
                    referring_doctor TEXT NOT NULL DEFAULT '',
                    referring_phone TEXT NOT NULL DEFAULT '',
                    tooth TEXT NOT NULL DEFAULT '',
                    referral_type TEXT NOT NULL DEFAULT '',
                    urgency TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    files_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_drlinq_referrals_specialist
                    ON drlinq_referrals(specialist_id, status, created_at);
                """
            )
            if not c.execute("SELECT 1 FROM drlinq_referral_specialists WHERE slug='demo-endo'").fetchone():
                ts = now()
                c.execute(
                    """INSERT INTO drlinq_referral_specialists(
                        id,slug,access_token,name,clinic_name,specialty,city,phone,active,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "spec_demo_endo",
                        "demo-endo",
                        "demo-no-admin-access",
                        "دکتر نمونه",
                        "مرکز تخصصی درمان ریشه دکتر لینک",
                        "endodontics",
                        "اهواز",
                        "",
                        1,
                        ts,
                        ts,
                    ),
                )

    init()

    def public_specialist(row):
        return {
            "id": row["id"],
            "slug": row["slug"],
            "name": row["name"],
            "clinicName": row["clinic_name"],
            "specialty": row["specialty"],
            "city": row["city"],
        }

    def auth(sid: str):
        token = clean(request.args.get("token") or request.headers.get("X-Referral-Token"), 220)
        with con() as c:
            row = c.execute(
                "SELECT * FROM drlinq_referral_specialists WHERE id=? AND active=1",
                (clean(sid, 160),),
            ).fetchone()
        if not row or not token or not secrets.compare_digest(token, row["access_token"]):
            return None
        return row

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
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Referral-Token"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @bp.route("/api/referral/<path:_p>", methods=["OPTIONS"])
    def options(_p):
        return ("", 204)

    @bp.get("/api/referral/health")
    def health():
        return jsonify(ok=True, service="drlinq-referral", version=VERSION, specialty="endodontics")

    @bp.post("/api/referral/specialists/register")
    def register_specialist():
        b = request.get_json(silent=True) or {}
        name = clean(b.get("name"), 160)
        if not name:
            return jsonify(error="name_required"), 400
        base = slugify(b.get("slug") or name)
        slug = base
        with con() as c:
            i = 2
            while c.execute("SELECT 1 FROM drlinq_referral_specialists WHERE slug=?", (slug,)).fetchone():
                slug = f"{base[:40]}-{i}"
                i += 1
            sid = f"spec_{int(time.time()*1000)}_{secrets.token_hex(5)}"
            token = secrets.token_urlsafe(26)
            ts = now()
            c.execute(
                """INSERT INTO drlinq_referral_specialists(
                    id,slug,access_token,name,clinic_name,specialty,city,phone,active,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    sid,
                    slug,
                    token,
                    name,
                    clean(b.get("clinicName"), 180),
                    "endodontics",
                    clean(b.get("city"), 100),
                    clean(b.get("phone"), 60),
                    1,
                    ts,
                    ts,
                ),
            )
        return jsonify(ok=True, specialistId=sid, accessToken=token, slug=slug)

    @bp.get("/api/referral/c/<slug>")
    def get_public(slug):
        with con() as c:
            row = c.execute(
                "SELECT * FROM drlinq_referral_specialists WHERE slug=? AND active=1",
                (clean(slug, 80),),
            ).fetchone()
        if not row:
            return jsonify(error="not_found"), 404
        return jsonify(ok=True, specialist=public_specialist(row))

    def save_uploads(referral_id: str):
        files_out = []
        files = request.files.getlist("files")[:MAX_FILES]
        dest = upload_root / referral_id
        dest.mkdir(parents=True, exist_ok=True)
        for f in files:
            if not f or not f.filename:
                continue
            original = clean(f.filename, 180)
            ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
            if ext not in ALLOWED_EXT:
                continue
            data = f.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                continue
            fid = f"file_{secrets.token_hex(8)}"
            stored = f"{fid}.{ext}"
            (dest / stored).write_bytes(data)
            files_out.append({"id": fid, "name": original, "stored": stored, "size": len(data), "type": clean(f.mimetype, 100)})
        return files_out

    @bp.post("/api/referral/c/<slug>/submit")
    def submit(slug):
        if request.content_length and request.content_length > (MAX_FILE_BYTES * MAX_FILES + 2 * 1024 * 1024):
            return jsonify(error="payload_too_large"), 413
        with con() as c:
            specialist = c.execute(
                "SELECT * FROM drlinq_referral_specialists WHERE slug=? AND active=1",
                (clean(slug, 80),),
            ).fetchone()
        if not specialist:
            return jsonify(error="not_found"), 404
        raw_payload = request.form.get("payload", "{}")
        payload = load_json(raw_payload, {})
        if not isinstance(payload, dict):
            payload = {}
        allowed = {
            "patientName", "patientPhone", "referringDoctor", "referringPhone", "tooth",
            "referralType", "workingDiagnosis", "tests", "symptoms", "problem", "problemDetail",
            "previousTreatment", "previousTreatmentDate", "radiographType", "urgency", "medicalNote",
            "restorativePlan", "instructions", "consent"
        }
        payload = {k: clean(payload.get(k), 1400) for k in allowed if k in payload}
        required = ["patientName", "referringDoctor", "tooth", "referralType", "urgency"]
        if any(not payload.get(k) for k in required):
            return jsonify(error="missing_required_fields"), 400
        if payload.get("consent") not in {"true", "1", "yes", "بله"}:
            return jsonify(error="consent_required"), 400
        rid = f"ref_{int(time.time()*1000)}_{secrets.token_hex(5)}"
        files_out = save_uploads(rid)
        ts = now()
        with con() as c:
            c.execute(
                """INSERT INTO drlinq_referrals(
                    id,specialist_id,patient_name,patient_phone,referring_doctor,referring_phone,
                    tooth,referral_type,urgency,payload_json,files_json,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rid,
                    specialist["id"],
                    payload.get("patientName", ""),
                    payload.get("patientPhone", ""),
                    payload.get("referringDoctor", ""),
                    payload.get("referringPhone", ""),
                    payload.get("tooth", ""),
                    payload.get("referralType", ""),
                    payload.get("urgency", ""),
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(files_out, ensure_ascii=False),
                    "new",
                    ts,
                    ts,
                ),
            )
        return jsonify(ok=True, referralId=rid, message="ارجاع با موفقیت برای متخصص ارسال شد.", filesReceived=len(files_out))

    @bp.get("/api/referral/specialists/<sid>/dashboard")
    def dashboard(sid):
        specialist = auth(sid)
        if not specialist:
            return jsonify(error="unauthorized"), 401
        with con() as c:
            rows = c.execute(
                "SELECT * FROM drlinq_referrals WHERE specialist_id=? ORDER BY created_at DESC LIMIT 200",
                (specialist["id"],),
            ).fetchall()
        refs = []
        for r in rows:
            refs.append({
                "id": r["id"],
                "patientName": r["patient_name"],
                "patientPhone": r["patient_phone"],
                "referringDoctor": r["referring_doctor"],
                "referringPhone": r["referring_phone"],
                "tooth": r["tooth"],
                "referralType": r["referral_type"],
                "urgency": r["urgency"],
                "payload": load_json(r["payload_json"], {}),
                "files": [{k: x.get(k) for k in ("id", "name", "size", "type")} for x in load_json(r["files_json"], [])],
                "status": r["status"],
                "createdAt": r["created_at"],
            })
        return jsonify(ok=True, specialist=public_specialist(specialist), referrals=refs)

    @bp.post("/api/referral/specialists/<sid>/referrals/<rid>/status")
    def update_status(sid, rid):
        specialist = auth(sid)
        if not specialist:
            return jsonify(error="unauthorized"), 401
        b = request.get_json(silent=True) or {}
        status = clean(b.get("status"), 30)
        if status not in {"new", "reviewed", "contacted", "scheduled", "treated", "closed"}:
            return jsonify(error="invalid_status"), 400
        with con() as c:
            cur = c.execute(
                "UPDATE drlinq_referrals SET status=?,updated_at=? WHERE id=? AND specialist_id=?",
                (status, now(), clean(rid, 160), specialist["id"]),
            )
        if not cur.rowcount:
            return jsonify(error="not_found"), 404
        return jsonify(ok=True, status=status)

    @bp.get("/api/referral/specialists/<sid>/referrals/<rid>/files/<fid>")
    def get_file(sid, rid, fid):
        specialist = auth(sid)
        if not specialist:
            return jsonify(error="unauthorized"), 401
        with con() as c:
            row = c.execute(
                "SELECT files_json FROM drlinq_referrals WHERE id=? AND specialist_id=?",
                (clean(rid, 160), specialist["id"]),
            ).fetchone()
        if not row:
            return jsonify(error="not_found"), 404
        files = load_json(row["files_json"], [])
        item = next((x for x in files if x.get("id") == clean(fid, 120)), None)
        if not item:
            return jsonify(error="file_not_found"), 404
        path = upload_root / clean(rid, 160) / clean(item.get("stored"), 220)
        if not path.exists() or not path.is_file():
            return jsonify(error="file_missing"), 404
        return send_file(path, as_attachment=True, download_name=clean(item.get("name"), 180) or path.name)

    return bp
