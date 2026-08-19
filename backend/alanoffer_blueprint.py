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


VERSION = "0.3.0"

# DrLinq MVP: demand first. We collect only what is needed to decide
# which providers should receive the request. Provider acquisition happens
# after a real request exists, not before.
BUYER_FLOW = [
    {
        "key": "service",
        "question": "چه خدمت یا درمانی می‌خوای؟",
        "hint": "مثلاً ایمپلنت، ترمیم دندان، لیزر پوست یا فیزیوتراپی",
        "options": ["ایمپلنت", "ترمیم دندان", "عصب‌کشی", "روکش", "ارتودنسی", "نمی‌دانم"],
        "multi": False,
    },
    {
        "key": "city",
        "question": "در کدوم شهر دنبال درمانگر می‌گردی؟",
        "hint": "فعلاً فقط مراکز استان‌ها پوشش داده می‌شوند.",
        "options": [],
        "multi": False,
    },
    {
        "key": "priorities",
        "question": "برای انتخاب درمانگر، کدوم چیزها برات مهم‌تره؟ حداکثر دو مورد.",
        "hint": "می‌تونی دو گزینه انتخاب کنی یا خودت بنویسی.",
        "options": ["قیمت بهتر", "کیفیت", "سرعت", "اقساط", "نزدیکی"],
        "multi": True,
    },
    {
        "key": "case_size",
        "question": "حجم کارت تقریباً چقدره؟",
        "hint": "مثلاً ۱ ایمپلنت، ۵ دندان، ۱۰ جلسه فیزیوتراپی؛ اگر نمی‌دونی هم اشکالی نداره.",
        "options": ["یک مورد", "۲ تا ۳ مورد", "۴ مورد یا بیشتر", "نمی‌دانم"],
        "multi": False,
    },
    {
        "key": "wait",
        "question": "تا کی می‌تونی برای پیدا شدن گزینه مناسب صبر کنی؟",
        "hint": "",
        "options": ["امروز", "تا ۳ روز", "تا یک هفته", "عجله ندارم"],
        "multi": False,
    },
    {
        "key": "contact",
        "question": "برای خبر دادن، شماره موبایل یا واتساپت رو بفرست.",
        "hint": "فقط برای پیگیری همین درخواست استفاده می‌شود.",
        "options": [],
        "multi": False,
    },
]

PROVINCE_CAPITALS = {
    "اراک", "اردبیل", "ارومیه", "اصفهان", "اهواز", "ایلام", "بجنورد", "بندرعباس",
    "بوشهر", "بیرجند", "تبریز", "تهران", "خرم آباد", "خرم‌آباد", "رشت", "زاهدان",
    "زنجان", "ساری", "سمنان", "سنندج", "شهرکرد", "شیراز", "قزوین", "قم", "کرج",
    "کرمان", "کرمانشاه", "گرگان", "مشهد", "همدان", "یاسوج", "یزد",
}


def create_alanoffer_blueprint(data_root: str | Path) -> Blueprint:
    """DrLinq demand-first MVP mounted on the existing /alanoffer path.

    The route prefix stays unchanged so the current Cloudiva integration does not
    break while the public brand and domain move to DrLinq.
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
            "https://hajizadehmasoud5-ui.github.io,https://drlinq.ir,https://www.drlinq.ir",
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
                    role TEXT NOT NULL DEFAULT 'buyer',
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
                    status TEXT NOT NULL DEFAULT 'needs_provider_search',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_records_role_created
                    ON chat_records(role, created_at);
                CREATE INDEX IF NOT EXISTS idx_chat_records_status_created
                    ON chat_records(status, created_at);
                """
            )

    init_db()

    def clean(value: Any, max_len: int = 300) -> str:
        text = re.sub(r"[\x00-\x1f]+", " ", str(value or ""))
        return re.sub(r"\s+", " ", text).strip()[:max_len]

    def norm(value: Any) -> str:
        return (
            clean(value, 800)
            .replace("ي", "ی")
            .replace("ك", "ک")
            .replace("ۀ", "ه")
            .lower()
        )

    def new_id(prefix: str) -> str:
        return f"{prefix}_{int(time.time() * 1000)}_{secrets.token_hex(5)}"

    def normalize_digits(value: Any) -> str:
        table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        return str(value or "").translate(table)

    def valid_contact(value: Any) -> bool:
        digits = re.sub(r"\D+", "", normalize_digits(value))
        return 10 <= len(digits) <= 15

    def supported_city(value: Any) -> bool:
        city = norm(value).replace("‌", " ")
        capitals = {norm(x).replace("‌", " ") for x in PROVINCE_CAPITALS}
        return city in capitals

    def next_question(data: dict[str, Any]) -> dict[str, Any] | None:
        for item in BUYER_FLOW:
            if not clean(data.get(item["key"]), 700):
                data["_awaiting"] = item["key"]
                return item
        data.pop("_awaiting", None)
        return None

    def question_payload(item: dict[str, Any]) -> dict[str, Any]:
        reply = item["question"]
        if item.get("hint"):
            reply += "\n" + item["hint"]
        return {
            "reply": reply,
            "field": item["key"],
            "options": item.get("options", []),
            "multi": bool(item.get("multi")),
        }

    def load_session(session_id: str) -> tuple[dict[str, Any], bool] | None:
        with connect() as con:
            row = con.execute(
                "SELECT data_json,ready FROM chat_sessions WHERE id=?",
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
        return data, bool(row["ready"])

    def save_session(session_id: str, data: dict[str, Any], ready: bool) -> None:
        now = int(time.time() * 1000)
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        with connect() as con:
            con.execute(
                "UPDATE chat_sessions SET role='buyer',data_json=?,ready=?,updated_at=? WHERE id=?",
                (payload, int(ready), now, session_id),
            )

    def priority_tags(value: Any) -> list[str]:
        n = norm(value)
        tags: list[str] = []
        mapping = [
            ("price", ["قیمت", "ارزان", "هزینه"]),
            ("quality", ["کیفیت", "اعتبار", "بهترین"]),
            ("speed", ["سرعت", "سریع", "زود"]),
            ("installment", ["اقساط", "قسط"]),
            ("distance", ["نزدیک", "نزدیکی", "مسافت"]),
        ]
        for tag, words in mapping:
            if any(word in n for word in words):
                tags.append(tag)
        return tags[:3]

    def save_record(session_id: str, data: dict[str, Any]) -> None:
        public_data = {k: v for k, v in data.items() if not k.startswith("_")}
        public_data["match_profile"] = {
            "service": clean(data.get("service"), 180),
            "city": clean(data.get("city"), 80),
            "priority_tags": priority_tags(data.get("priorities")),
            "case_size": clean(data.get("case_size"), 160),
            "wait": clean(data.get("wait"), 100),
        }
        with connect() as con:
            con.execute(
                """
                INSERT OR IGNORE INTO chat_records(id,session_id,role,payload_json,status,created_at)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    new_id("drq"),
                    session_id,
                    "buyer",
                    json.dumps(public_data, ensure_ascii=False),
                    "needs_provider_search",
                    int(time.time() * 1000),
                ),
            )

    def summary(data: dict[str, Any]) -> str:
        return (
            f"{clean(data.get('service'), 120)} | "
            f"{clean(data.get('city'), 70)} | "
            f"اولویت: {clean(data.get('priorities'), 120)} | "
            f"حجم: {clean(data.get('case_size'), 120)} | "
            f"مهلت: {clean(data.get('wait'), 90)}"
        )

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
            service="drlinq-request-intake",
            version=VERSION,
            mode="demand-first-mvp",
            ai=False,
            coverage="iran-province-capitals",
            db=True,
            records=records,
            time=time.time(),
        )

    @bp.post("/api/chat/start")
    def chat_start():
        session_id = new_id("cs")
        now = int(time.time() * 1000)
        data: dict[str, Any] = {}
        with connect() as con:
            con.execute("DELETE FROM chat_sessions WHERE updated_at<?", (now - 30 * 24 * 3600 * 1000,))
            con.execute(
                "INSERT INTO chat_sessions(id,role,data_json,ready,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (session_id, "buyer", "{}", 0, now, now),
            )
        item = next_question(data)
        save_session(session_id, data, False)
        payload = question_payload(item or BUYER_FLOW[0])
        return jsonify(ok=True, sessionId=session_id, role="buyer", ready=False, **payload)

    @bp.post("/api/chat/message")
    def chat_message():
        body = request.get_json(silent=True) or {}
        session_id = clean(body.get("sessionId"), 120)
        text = clean(body.get("text"), 1200)
        if not session_id or not text:
            return jsonify(error="missing_session_or_text"), 400

        loaded = load_session(session_id)
        if not loaded:
            return jsonify(error="session_not_found"), 404
        data, was_ready = loaded

        if was_ready:
            return jsonify(
                ok=True,
                sessionId=session_id,
                role="buyer",
                reply="این درخواست قبلاً ثبت شده. برای درخواست جدید «شروع تازه» رو بزن.",
                ready=True,
                summary=summary(data),
            )

        awaiting = clean(data.get("_awaiting"), 40)
        valid_keys = {item["key"] for item in BUYER_FLOW}
        if awaiting not in valid_keys:
            item = next_question(data)
            if item:
                save_session(session_id, data, False)
                return jsonify(ok=True, sessionId=session_id, role="buyer", ready=False, **question_payload(item))
            awaiting = ""

        if awaiting == "contact" and not valid_contact(text):
            return jsonify(
                ok=True,
                sessionId=session_id,
                role="buyer",
                reply="یک شماره موبایل یا واتساپ معتبر بفرست؛ فقط شماره کافیه.",
                field="contact",
                options=[],
                multi=False,
                ready=False,
            )

        if awaiting == "city" and not supported_city(text):
            return jsonify(
                ok=True,
                sessionId=session_id,
                role="buyer",
                reply="فعلاً فقط مراکز استان‌ها رو پوشش می‌دیم. اسم مرکز استان رو بنویس؛ مثلاً اهواز، شیراز یا تهران.",
                field="city",
                options=[],
                multi=False,
                ready=False,
            )

        if awaiting:
            data[awaiting] = text
            data.pop("_awaiting", None)

        item = next_question(data)
        if item:
            save_session(session_id, data, False)
            return jsonify(ok=True, sessionId=session_id, role="buyer", ready=False, **question_payload(item))

        save_record(session_id, data)
        save_session(session_id, data, True)
        return jsonify(
            ok=True,
            sessionId=session_id,
            role="buyer",
            reply=(
                "درخواستت ثبت شد. ما بر اساس شهر، نوع درمان و اولویت‌هات سراغ درمانگرهای مناسب می‌ریم. "
                "اگر گزینه‌ای برای بررسی درخواستت اعلام آمادگی کرد، بهت خبر می‌دیم."
            ),
            ready=True,
            summary=summary(data),
            field=None,
            options=[],
            multi=False,
            status="needs_provider_search",
        )

    return bp
