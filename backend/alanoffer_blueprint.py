from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request


VERSION = "0.2.0"
BUYER_FLOW = [
    ("need", "دقیقاً چی می‌خوای؟ یک جمله کافیه.", "What exactly do you need? One sentence is enough."),
    ("city", "کدوم شهر هستی؟", "Which city are you in?"),
    ("area", "کدوم محله یا منطقه؟ اگر فرقی نداره بنویس «فرقی نداره».", "Which neighborhood or area? If it does not matter, say 'any'."),
    ("wait", "تا کی می‌تونی صبر کنی؟ مثلاً امروز، ۳ روز یا یک هفته.", "How long can you wait? For example today, 3 days, or a week."),
    ("contact", "برای خبر دادن یک شماره موبایل یا واتساپ بفرست.", "Send a mobile or WhatsApp number so we can notify you."),
]
SELLER_FLOW = [
    ("business_name", "اسم کسب‌وکارت چیه؟", "What is your business name?"),
    ("offer", "الان دقیقاً چه محصول، خدمت یا ظرفیت خالی داری؟", "What product, service, or unused capacity do you have right now?"),
    ("city", "کسب‌وکارت در کدوم شهره؟", "Which city is your business in?"),
    ("area", "کدوم محله یا منطقه؟", "Which neighborhood or area?"),
    ("price", "قیمت عادی و قیمت پیشنهادی رو باهم بنویس؛ مثلاً ۵۰۰ → ۳۵۰ هزار تومان.", "Send the normal price and offer price together, e.g. 500 -> 350."),
    ("availability", "چندتا ظرفیت/موجودی داری و تا کی معتبره؟", "How much capacity/stock is available and until when?"),
    ("contact", "یک شماره موبایل یا واتساپ برای پیگیری بفرست.", "Send a mobile or WhatsApp number for follow-up."),
]


def create_alanoffer_blueprint(data_root: str | Path) -> Blueprint:
    """Minimal AlanOffer Chat-first backend for the existing Cloudiva Flask app.

    Mount under /alanoffer. Data is stored centrally in SQLite so buyer/seller
    sessions no longer depend on browser localStorage.
    """
    bp = Blueprint("alanoffer", __name__, url_prefix="/alanoffer")
    root = Path(data_root) / "alanoffer"
    root.mkdir(parents=True, exist_ok=True)
    db_path = Path(os.environ.get("ALANOFFER_DB_PATH", str(root / "alanoffer.db")))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    allowed_origins = {
        x.strip()
        for x in os.environ.get(
            "ALANOFFER_CORS_ORIGINS",
            "https://hajizadehmasoud5-ui.github.io",
        ).split(",")
        if x.strip()
    }

    def connect() -> sqlite3.Connection:
        con = sqlite3.connect(str(db_path), timeout=20)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def init_db() -> None:
        with connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions(
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL DEFAULT 'unknown',
                    data_json TEXT NOT NULL DEFAULT '{}',
                    ready INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated
                    ON chat_sessions(updated_at);

                CREATE TABLE IF NOT EXISTS chat_records(
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_records_role_created
                    ON chat_records(role, created_at);
                """
            )

    init_db()

    def clean(value: Any, max_len: int = 300) -> str:
        text = re.sub(r"[\x00-\x1f]+", " ", str(value or ""))
        return re.sub(r"\s+", " ", text).strip()[:max_len]

    def norm(value: Any) -> str:
        return clean(value, 800).replace("ي", "ی").replace("ك", "ک").lower()

    def new_id(prefix: str) -> str:
        return f"{prefix}_{int(time.time() * 1000)}_{secrets.token_hex(5)}"

    def normalize_digits(value: Any) -> str:
        table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        return str(value or "").translate(table)

    def valid_contact(value: Any) -> bool:
        digits = re.sub(r"\D+", "", normalize_digits(value))
        return 10 <= len(digits) <= 15

    def language(text: str) -> str:
        latin = sum(1 for ch in text if "a" <= ch.lower() <= "z")
        rtl = sum(1 for ch in text if "\u0600" <= ch <= "\u06ff")
        return "en" if latin > rtl * 1.4 and latin >= 3 else "fa"

    def infer_role(text: str) -> str:
        n = norm(text)
        seller_words = [
            "کسب و کار", "کسب‌وکار", "فروشگاه", "مغازه", "رستوران دارم",
            "کلینیک دارم", "فروشنده", "می فروشم", "می‌فروشم",
            "business", "seller", "shop owner", "merchant",
        ]
        buyer_words = [
            "میخوام", "می خوام", "می‌خوام", "لازم دارم", "دنبال",
            "need", "want", "looking for", "buyer",
        ]
        if any(word in n for word in seller_words):
            return "seller"
        if any(word in n for word in buyer_words):
            return "buyer"
        return "unknown"

    def flow(role: str):
        return SELLER_FLOW if role == "seller" else BUYER_FLOW

    def next_question(role: str, data: dict[str, Any], lang: str) -> tuple[str | None, str]:
        for key, fa, en in flow(role):
            if not clean(data.get(key), 600):
                data["_awaiting"] = key
                return key, en if lang == "en" else fa
        data.pop("_awaiting", None)
        return None, ""

    def load_session(session_id: str) -> tuple[str, dict[str, Any], bool] | None:
        with connect() as con:
            row = con.execute(
                "SELECT role,data_json,ready FROM chat_sessions WHERE id=?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["data_json"] or "{}")
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        return clean(row["role"], 20) or "unknown", data, bool(row["ready"])

    def save_session(session_id: str, role: str, data: dict[str, Any], ready: bool) -> None:
        now = int(time.time() * 1000)
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        with connect() as con:
            con.execute(
                "UPDATE chat_sessions SET role=?,data_json=?,ready=?,updated_at=? WHERE id=?",
                (role, payload, int(ready), now, session_id),
            )

    def save_record(session_id: str, role: str, data: dict[str, Any]) -> None:
        public_data = {k: v for k, v in data.items() if not k.startswith("_")}
        with connect() as con:
            con.execute(
                """
                INSERT OR IGNORE INTO chat_records(id,session_id,role,payload_json,status,created_at)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    new_id("cr"), session_id, role,
                    json.dumps(public_data, ensure_ascii=False),
                    "new", int(time.time() * 1000),
                ),
            )

    def summary(role: str, data: dict[str, Any]) -> str:
        if role == "seller":
            parts = [
                f"کسب‌وکار: {clean(data.get('business_name'), 120)}",
                f"آفر: {clean(data.get('offer'), 180)}",
                f"مکان: {clean(data.get('city'), 80)}، {clean(data.get('area'), 100)}",
                f"قیمت: {clean(data.get('price'), 120)}",
                f"ظرفیت: {clean(data.get('availability'), 160)}",
            ]
        else:
            parts = [
                f"درخواست: {clean(data.get('need'), 180)}",
                f"مکان: {clean(data.get('city'), 80)}، {clean(data.get('area'), 100)}",
                f"مهلت: {clean(data.get('wait'), 100)}",
            ]
        return " | ".join(parts)

    @bp.after_request
    def cors(resp):
        origin = request.headers.get("Origin", "")
        if origin in allowed_origins:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @bp.route("/api/<path:_path>", methods=["OPTIONS"])
    def options(_path: str):
        return ("", 204)

    @bp.get("/api/health")
    @bp.get("/api/chat/health")
    def health():
        with connect() as con:
            records = con.execute("SELECT COUNT(*) AS n FROM chat_records").fetchone()["n"]
        return jsonify(
            ok=True,
            service="alanoffer-chat",
            version=VERSION,
            mode="structured-mvp",
            ai=False,
            scope="iran",
            db=True,
            records=records,
            time=time.time(),
        )

    @bp.post("/api/chat/start")
    def chat_start():
        body = request.get_json(silent=True) or {}
        role = clean(body.get("role"), 20).lower()
        if role not in {"buyer", "seller"}:
            role = "unknown"
        session_id = new_id("cs")
        now = int(time.time() * 1000)
        data: dict[str, Any] = {}
        with connect() as con:
            # Sessions are temporary; records remain as the structured MVP data.
            con.execute("DELETE FROM chat_sessions WHERE updated_at<?", (now - 30 * 24 * 3600 * 1000,))
            con.execute(
                "INSERT INTO chat_sessions(id,role,data_json,ready,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (session_id, role, "{}", 0, now, now),
            )
        if role == "unknown":
            reply = "دنبال چیزی هستی یا کسب‌وکار داری؟ هرطور راحتی بگو."
        else:
            _, reply = next_question(role, data, "fa")
            save_session(session_id, role, data, False)
        return jsonify(ok=True, sessionId=session_id, role=role, reply=reply, ready=False)

    @bp.post("/api/chat/message")
    def chat_message():
        body = request.get_json(silent=True) or {}
        session_id = clean(body.get("sessionId"), 120)
        text = clean(body.get("text"), 1200)
        supplied_role = clean(body.get("role"), 20).lower()
        if not session_id or not text:
            return jsonify(error="missing_session_or_text"), 400

        loaded = load_session(session_id)
        if not loaded:
            return jsonify(error="session_not_found"), 404
        role, data, was_ready = loaded
        lang = language(text)

        if was_ready:
            done_text = "This request is already complete. Start a fresh chat for another request." if lang == "en" else "این درخواست قبلاً کامل شده. برای درخواست تازه، «شروع تازه» را بزن."
            return jsonify(ok=True, sessionId=session_id, role=role, reply=done_text, ready=True, summary=summary(role, data))

        if supplied_role in {"buyer", "seller"}:
            role = supplied_role

        if role not in {"buyer", "seller"}:
            role = infer_role(text)
            if role == "unknown":
                reply = "Are you looking for something, or do you own a business?" if lang == "en" else "فقط مشخص کن: دنبال چیزی هستی یا کسب‌وکار داری؟"
                return jsonify(ok=True, sessionId=session_id, role="unknown", reply=reply, ready=False)
            if role == "buyer":
                data["need"] = text
            else:
                data["opening"] = text
        else:
            awaiting = clean(data.get("_awaiting"), 40)
            valid_keys = {item[0] for item in flow(role)}
            if awaiting in valid_keys:
                if awaiting == "contact" and not valid_contact(text):
                    retry = "Please send a valid mobile or WhatsApp number." if lang == "en" else "یک شماره موبایل یا واتساپ معتبر بفرست؛ فقط شماره کافیه."
                    return jsonify(ok=True, sessionId=session_id, role=role, reply=retry, ready=False)
                data[awaiting] = text
                data.pop("_awaiting", None)
            elif role == "buyer" and not data.get("need"):
                data["need"] = text
            elif role == "seller" and not data.get("offer"):
                data["offer"] = text
            else:
                notes = (clean(data.get("notes"), 1000) + " | " + text).strip(" |")
                data["notes"] = notes[:1200]

        key, question = next_question(role, data, lang)
        if key is not None:
            save_session(session_id, role, data, False)
            return jsonify(ok=True, sessionId=session_id, role=role, reply=question, ready=False)

        save_record(session_id, role, data)
        save_session(session_id, role, data, True)
        reply = "Saved. This MVP now stores the structured request; real matching and notifications are the next step." if lang == "en" else "ثبت شد. اطلاعات ساختاریافته ذخیره شد؛ مرحله بعد Match و اعلان واقعی است."
        return jsonify(ok=True, sessionId=session_id, role=role, reply=reply, ready=True, summary=summary(role, data))

    return bp
