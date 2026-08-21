from __future__ import annotations

import base64
import json
import re
import sqlite3
import threading
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from flask import Blueprint, jsonify, request
from pywebpush import WebPushException, webpush

VERSION = "0.2.0"
POLL_SECONDS = 5


def create_drlinq_push_blueprint(data_root: str | Path) -> Blueprint:
    bp = Blueprint("drlinq_push", __name__, url_prefix="/alanoffer/api/referral/push")
    root = Path(data_root) / "alanoffer"
    root.mkdir(parents=True, exist_ok=True)
    db = root / "alanoffer.db"
    vapid_path = root / "drlinq_vapid_private.pem"

    def con():
        c = sqlite3.connect(str(db), timeout=20)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def now() -> int:
        return int(time.time() * 1000)

    def clean(v, n=500) -> str:
        return re.sub(r"\s+", " ", str(v or "")).strip()[:n]

    def init_db():
        with con() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS drlinq_push_subscriptions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    specialist_id TEXT NOT NULL,
                    endpoint TEXT NOT NULL UNIQUE,
                    p256dh TEXT NOT NULL,
                    auth TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_drlinq_push_specialist
                    ON drlinq_push_subscriptions(specialist_id, created_at);

                CREATE TABLE IF NOT EXISTS drlinq_push_deliveries(
                    subscription_id INTEGER NOT NULL,
                    referral_id TEXT NOT NULL,
                    delivered_at INTEGER NOT NULL,
                    PRIMARY KEY(subscription_id, referral_id)
                );
                """
            )

    def ensure_vapid_key():
        """Keep one stable P-256 VAPID key and serialize it in py_vapid-compatible EC PEM form."""
        private_key = None
        if vapid_path.exists():
            try:
                private_key = serialization.load_pem_private_key(vapid_path.read_bytes(), password=None)
            except Exception:
                private_key = None
        if private_key is None:
            private_key = ec.generate_private_key(ec.SECP256R1())
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        if not vapid_path.exists() or vapid_path.read_bytes() != pem:
            tmp = vapid_path.with_suffix(".tmp")
            tmp.write_bytes(pem)
            tmp.replace(vapid_path)

    def public_key_b64() -> str:
        private_key = serialization.load_pem_private_key(vapid_path.read_bytes(), password=None)
        raw = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def specialist_auth(sid: str):
        token = clean(request.args.get("token") or request.headers.get("X-Referral-Token"), 300)
        with con() as c:
            row = c.execute(
                "SELECT * FROM drlinq_referral_specialists WHERE id=? AND active=1",
                (clean(sid, 180),),
            ).fetchone()
        if not row or not token:
            return None
        import secrets
        if not secrets.compare_digest(token, row["access_token"]):
            return None
        return row

    def send_push(subscription: dict, title: str, body: str, url: str = "/shahmoradi-panel.html") -> tuple[bool, int | None, str]:
        payload = json.dumps(
            {"title": title, "body": body, "url": url, "tag": "drlinq-referral"},
            ensure_ascii=False,
        )
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription["endpoint"],
                    "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
                },
                data=payload,
                vapid_private_key=str(vapid_path),
                vapid_claims={"sub": "mailto:push@drlinq.ir"},
                ttl=300,
                timeout=12,
            )
            return True, None, ""
        except WebPushException as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            detail = clean(getattr(getattr(exc, "response", None), "text", "") or str(exc), 350)
            return False, code, detail
        except Exception as exc:
            return False, None, clean(f"{type(exc).__name__}: {exc}", 350)

    def process_pending_once():
        with con() as c:
            subscriptions = c.execute(
                "SELECT * FROM drlinq_push_subscriptions ORDER BY id"
            ).fetchall()
        for sub in subscriptions:
            with con() as c:
                rows = c.execute(
                    """
                    SELECT r.id,r.tooth,r.urgency,r.created_at
                    FROM drlinq_referrals r
                    WHERE r.specialist_id=?
                      AND r.created_at>=?
                      AND NOT EXISTS(
                        SELECT 1 FROM drlinq_push_deliveries d
                        WHERE d.subscription_id=? AND d.referral_id=r.id
                      )
                    ORDER BY r.created_at ASC
                    LIMIT 20
                    """,
                    (sub["specialist_id"], sub["created_at"], sub["id"]),
                ).fetchall()
            for r in rows:
                body = "ارجاع جدید درمان ریشه"
                if r["tooth"]:
                    body += f" • دندان {r['tooth']}"
                if r["urgency"]:
                    body += f" • {r['urgency']}"
                ok, code, _detail = send_push(dict(sub), "ارجاع جدید در دکتر لینک", body)
                if ok:
                    with con() as c:
                        c.execute(
                            "INSERT OR IGNORE INTO drlinq_push_deliveries(subscription_id,referral_id,delivered_at) VALUES(?,?,?)",
                            (sub["id"], r["id"], now()),
                        )
                elif code in {404, 410}:
                    with con() as c:
                        c.execute("DELETE FROM drlinq_push_subscriptions WHERE id=?", (sub["id"],))
                    break

    def worker():
        while True:
            try:
                process_pending_once()
            except Exception:
                pass
            time.sleep(POLL_SECONDS)

    init_db()
    ensure_vapid_key()
    threading.Thread(target=worker, name="drlinq-push", daemon=True).start()

    @bp.after_request
    def no_store(resp):
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @bp.get("/health")
    def health():
        with con() as c:
            n = c.execute("SELECT COUNT(*) n FROM drlinq_push_subscriptions").fetchone()["n"]
        return jsonify(ok=True, service="drlinq-push", version=VERSION, subscriptions=n)

    @bp.get("/public-key")
    def public_key():
        return jsonify(ok=True, publicKey=public_key_b64())

    @bp.post("/subscribe/<sid>")
    def subscribe(sid):
        specialist = specialist_auth(sid)
        if not specialist:
            return jsonify(error="unauthorized"), 401
        b = request.get_json(silent=True) or {}
        endpoint = str(b.get("endpoint") or "")[:3000]
        keys = b.get("keys") or {}
        p256dh = str(keys.get("p256dh") or "")[:1000]
        auth_key = str(keys.get("auth") or "")[:500]
        if not endpoint or not p256dh or not auth_key:
            return jsonify(error="invalid_subscription"), 400
        ts = now()
        with con() as c:
            c.execute(
                """
                INSERT INTO drlinq_push_subscriptions(specialist_id,endpoint,p256dh,auth,created_at,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(endpoint) DO UPDATE SET
                    specialist_id=excluded.specialist_id,
                    p256dh=excluded.p256dh,
                    auth=excluded.auth,
                    updated_at=excluded.updated_at
                """,
                (specialist["id"], endpoint, p256dh, auth_key, ts, ts),
            )
            row = c.execute("SELECT * FROM drlinq_push_subscriptions WHERE endpoint=?", (endpoint,)).fetchone()
        ok, code, detail = send_push(dict(row), "دکتر لینک", "نوتیفیکیشن ارجاع‌های جدید فعال شد.")
        return jsonify(ok=True, testPushSent=ok, testPushCode=code, testPushError=detail)

    @bp.post("/test/<sid>")
    def test_push(sid):
        specialist = specialist_auth(sid)
        if not specialist:
            return jsonify(error="unauthorized"), 401
        with con() as c:
            rows = c.execute(
                "SELECT * FROM drlinq_push_subscriptions WHERE specialist_id=? ORDER BY id",
                (specialist["id"],),
            ).fetchall()
        sent = 0
        failures = []
        for row in rows:
            ok, code, detail = send_push(dict(row), "تست اعلان دکتر لینک", "اگر این پیام را می‌بینید، اعلان ارجاع‌ها فعال است.")
            if ok:
                sent += 1
            else:
                failures.append({"code": code, "detail": detail})
                if code in {404, 410}:
                    with con() as c:
                        c.execute("DELETE FROM drlinq_push_subscriptions WHERE id=?", (row["id"],))
        return jsonify(ok=True, subscriptions=len(rows), sent=sent, failed=len(failures), failures=failures[:3])

    @bp.post("/unsubscribe/<sid>")
    def unsubscribe(sid):
        specialist = specialist_auth(sid)
        if not specialist:
            return jsonify(error="unauthorized"), 401
        b = request.get_json(silent=True) or {}
        endpoint = str(b.get("endpoint") or "")[:3000]
        with con() as c:
            c.execute(
                "DELETE FROM drlinq_push_subscriptions WHERE specialist_id=? AND endpoint=?",
                (specialist["id"], endpoint),
            )
        return jsonify(ok=True)

    return bp
