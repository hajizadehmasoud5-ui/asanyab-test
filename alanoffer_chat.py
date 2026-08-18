from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import requests
from flask import Blueprint, jsonify, request


def create_alanoffer_chat_blueprint(data_root: str | Path) -> Blueprint:
    bp = Blueprint("alanoffer_chat", __name__, url_prefix="/alanoffer")
    root = Path(data_root) / "alanoffer"
    root.mkdir(parents=True, exist_ok=True)
    db_path = Path(os.environ.get("ALANOFFER_DB_PATH", str(root / "alanoffer.db")))
    avalai_base = os.environ.get("AVALAI_BASE_URL", "https://api.avalai.ir/v1").rstrip("/")
    avalai_model = os.environ.get("AVALAI_MODEL", "gpt-5.4-mini")
    cors_origins = {
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
                    language TEXT NOT NULL DEFAULT '',
                    data_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_messages(
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);
                CREATE TABLE IF NOT EXISTS chat_leads(
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_leads_session ON chat_leads(session_id);
                """
            )

    init_db()

    def clean(v: Any, n: int = 1200) -> str:
        s = re.sub(r"[\x00-\x1f]+", " ", str(v or ""))
        return re.sub(r"\s+", " ", s).strip()[:n]

    def api_key() -> str:
        return os.environ.get("AVALAI_API_KEY", "").strip()

    def read_history(session_id: str, limit: int = 18) -> list[dict[str, str]]:
        with connect() as con:
            rows = con.execute(
                "SELECT sender,text FROM chat_messages WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        rows = list(reversed(rows))
        return [{"role": "assistant" if r["sender"] == "assistant" else "user", "content": r["text"]} for r in rows]

    def save_message(session_id: str, sender: str, text: str) -> None:
        with connect() as con:
            con.execute(
                "INSERT INTO chat_messages(id,session_id,sender,text,created_at) VALUES(?,?,?,?,?)",
                ("cm_" + uuid.uuid4().hex[:18], session_id, sender, clean(text, 3000), int(time.time() * 1000)),
            )

    def session_data(session_id: str) -> dict[str, Any]:
        with connect() as con:
            row = con.execute("SELECT * FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return {}
        try:
            return json.loads(row["data_json"] or "{}")
        except Exception:
            return {}

    SYSTEM = """تو هسته گفت‌وگویی AlanOffer هستی؛ یک واسطه بسیار ساده، باهوش و مذاکره‌کننده بین خریدار/متقاضی و فروشنده/کسب‌وکار.

اصل محصول: کاربر فقط حرف می‌زند؛ تو باید منظورش را بفهمی و کمترین سؤال ممکن را بپرسی.

قوانین:
1) زبان کاربر را تشخیص بده و دقیقاً به همان زبان جواب بده؛ فارسی، عربی، انگلیسی و زبان‌های دیگر.
2) اگر نقش روشن نیست، از متن تشخیص بده: buyer یعنی کسی که کالا/خدمت می‌خواهد؛ seller یعنی صاحب کسب‌وکار/ارائه‌دهنده. فقط اگر واقعاً مبهم بود یک سؤال کوتاه بپرس.
3) هر بار فقط یک سؤالِ ضروری بپرس. فرم و فهرست سؤال نساز.
4) اطلاعاتی که کاربر قبلاً گفته دوباره نپرس.
5) برای buyer حداقل اینها را در طول گفت‌وگو بفهم: نیاز واقعی، مکان تا حد لازم، زمان/فوریت، بودجه اگر مهم است، شرط مهم، راه تماس. همه موارد همیشه اجباری نیستند؛ با قضاوت خودت فقط چیزهای لازم را بپرس.
6) برای seller حداقل اینها را بفهم: چه چیزی می‌فروشد/ارائه می‌دهد، محدوده خدمت، ظرفیت یا زمان قابل ارائه، قیمت/پیشنهاد، مزیت یا امتیاز قابل ارائه، راه تماس. نام کسب‌وکار اگر طبیعی بود بگیر.
7) مذاکره کن، ولی مؤدب و کوتاه. اگر پیشنهاد فروشنده ضعیف است، یک پیشنهاد مشخص برای بهتر شدن آفر بده؛ مثل امتیاز اضافه، زمان کم‌تقاضا، باندل، ظرفیت محدود یا تخفیف واقعی. قیمت بازار، تخفیف، موجودی یا تأیید جعلی نساز.
8) برای خدمات حساس مثل پزشکی نقش تشخیص/درمان نداشته باش؛ فقط نیاز، ترجیح، موقعیت و بودجه/زمان را برای تطبیق با ارائه‌دهنده جمع کن.
9) وقتی اطلاعات کافی شد، ready=true کن، یک جمع‌بندی خیلی کوتاه بده و بگو درخواست/پیشنهاد ثبت شد و در صورت پیدا شدن تطبیق مناسب خبر می‌دهیم. ادعا نکن که همین الان فروشنده یا مشتری واقعی پیدا شده مگر داده‌ای برایش داشته باشی.
10) پاسخ باید کوتاه، انسانی و ساده باشد؛ معمولاً یک یا دو جمله.

فقط JSON معتبر برگردان با این ساختار:
{
  "reply":"متن کوتاه برای کاربر",
  "role":"buyer|seller|unknown",
  "language":"fa|ar|en|other",
  "ready":false,
  "summary":"جمع‌بندی کوتاه یا خالی",
  "data":{
    "need":"",
    "category":"",
    "country":"",
    "province":"",
    "city":"",
    "area":"",
    "budget":"",
    "deadline":"",
    "preferences":"",
    "business_name":"",
    "service":"",
    "service_area":"",
    "normal_price":"",
    "offer":"",
    "capacity":"",
    "conditions":"",
    "contact":"",
    "instagram":""
  }
}
داده‌های قبلی را حفظ کن و فقط با اطلاعات جدید اصلاح/تکمیل کن."""

    def fallback(role_hint: str, text: str, prev: dict[str, Any]) -> dict[str, Any]:
        role = role_hint if role_hint in {"buyer", "seller"} else prev.get("role", "unknown")
        low = text.lower()
        if role == "unknown":
            if any(x in low for x in ["دارم", "فروش", "مغازه", "کسب", "ارائه می", "clinic", "shop", "seller"]):
                role = "seller"
            else:
                role = "buyer"
        data = dict(prev.get("data") or {})
        if role == "buyer":
            data["need"] = data.get("need") or text
            reply = "کجایی یا این خدمت/کالا را در کدام شهر می‌خواهی؟"
        else:
            data["service"] = data.get("service") or text
            reply = "کسب‌وکارت در کدام شهر یا محدوده خدمات می‌دهد؟"
        return {"reply": reply, "role": role, "language": "fa", "ready": False, "summary": "", "data": data}

    def ask_ai(session_id: str, role_hint: str, text: str, prior: dict[str, Any]) -> dict[str, Any]:
        if not api_key():
            return fallback(role_hint, text, prior)
        history = read_history(session_id)
        context = {
            "role_hint": role_hint,
            "known": prior,
            "new_message": text,
        }
        messages = [{"role": "system", "content": SYSTEM}]
        messages.extend(history[-12:])
        messages.append({"role": "user", "content": "وضعیت ساختاری فعلی و پیام جدید:\n" + json.dumps(context, ensure_ascii=False)})
        r = requests.post(
            avalai_base + "/chat/completions",
            headers={"Authorization": "Bearer " + api_key(), "Content-Type": "application/json"},
            json={
                "model": avalai_model,
                "messages": messages,
                "temperature": 0.25,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        if not r.ok:
            raise RuntimeError(f"AvalAI {r.status_code}: {r.text[:180]}")
        raw = r.json()["choices"][0]["message"]["content"]
        out = json.loads(raw)
        if out.get("role") not in {"buyer", "seller", "unknown"}:
            out["role"] = "unknown"
        if not isinstance(out.get("data"), dict):
            out["data"] = {}
        out["reply"] = clean(out.get("reply"), 800)
        out["summary"] = clean(out.get("summary"), 800)
        out["ready"] = bool(out.get("ready"))
        return out

    def save_state(session_id: str, out: dict[str, Any]) -> None:
        now = int(time.time() * 1000)
        payload = json.dumps({"role": out.get("role"), "data": out.get("data") or {}}, ensure_ascii=False)
        with connect() as con:
            con.execute(
                "UPDATE chat_sessions SET role=?,language=?,data_json=?,status=?,updated_at=? WHERE id=?",
                (
                    out.get("role", "unknown"),
                    out.get("language", ""),
                    payload,
                    "ready" if out.get("ready") else "active",
                    now,
                    session_id,
                ),
            )
            if out.get("ready"):
                con.execute(
                    """
                    INSERT INTO chat_leads(id,session_id,role,summary,data_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(session_id) DO UPDATE SET role=excluded.role,summary=excluded.summary,data_json=excluded.data_json,updated_at=excluded.updated_at
                    """,
                    (
                        "cl_" + uuid.uuid4().hex[:18],
                        session_id,
                        out.get("role", "unknown"),
                        out.get("summary", ""),
                        json.dumps(out.get("data") or {}, ensure_ascii=False),
                        now,
                        now,
                    ),
                )

    @bp.after_request
    def cors(resp):
        origin = request.headers.get("Origin", "")
        if origin in cors_origins:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @bp.route("/api/chat/<path:_path>", methods=["OPTIONS"])
    def options(_path: str):
        return ("", 204)

    @bp.get("/api/chat/health")
    def health():
        return jsonify(ok=True, ai=bool(api_key()), model=avalai_model)

    @bp.post("/api/chat/start")
    def start():
        b = request.get_json(silent=True) or {}
        role_hint = clean(b.get("role"), 20)
        sid = "ac_" + uuid.uuid4().hex[:18]
        now = int(time.time() * 1000)
        with connect() as con:
            con.execute(
                "INSERT INTO chat_sessions(id,role,created_at,updated_at) VALUES(?,?,?,?)",
                (sid, role_hint if role_hint in {"buyer", "seller"} else "unknown", now, now),
            )
        if role_hint == "seller":
            greeting = "سلام 👋 کسب‌وکارت رو خیلی ساده معرفی کن؛ چی ارائه می‌دی و کجایی؟"
        elif role_hint == "buyer":
            greeting = "سلام 👋 فقط بگو چی می‌خوای. لازم نیست فرم پر کنی."
        else:
            greeting = "سلام 👋 هرچی می‌خوای همین‌جا بگو؛ اگر کسب‌وکار داری هم مستقیم معرفی‌اش کن."
        save_message(sid, "assistant", greeting)
        return jsonify(ok=True, sessionId=sid, reply=greeting, role=role_hint or "unknown"), 201

    @bp.post("/api/chat/message")
    def message():
        b = request.get_json(silent=True) or {}
        sid = clean(b.get("sessionId"), 80)
        text = clean(b.get("text"), 1500)
        role_hint = clean(b.get("role"), 20)
        if not sid or len(text) < 1:
            return jsonify(error="message_required"), 400
        with connect() as con:
            row = con.execute("SELECT id FROM chat_sessions WHERE id=?", (sid,)).fetchone()
        if not row:
            return jsonify(error="session_not_found"), 404
        prior = session_data(sid)
        save_message(sid, "user", text)
        try:
            out = ask_ai(sid, role_hint, text, prior)
        except Exception as exc:
            out = fallback(role_hint, text, prior)
            out["degraded"] = True
            out["debug"] = clean(type(exc).__name__, 80)
        save_message(sid, "assistant", out["reply"])
        save_state(sid, out)
        return jsonify(ok=True, sessionId=sid, **out)

    return bp
