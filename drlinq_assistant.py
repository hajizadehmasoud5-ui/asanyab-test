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

PACKAGES = {
    "implant": {
        "label": "ایمپلنت",
        "docs": ["رادیوگرافی پانورامیک (OPG) در صورت وجود", "CBCT در صورت درخواست پزشک", "فهرست داروهای مصرفی", "سوابق بیماری‌های مهم"],
        "fields": [
            ("count", "چند دندان نیاز به بررسی برای ایمپلنت دارد؟", ["یک دندان", "۲ تا ۳ دندان", "بیشتر از ۳ دندان", "نمی‌دانم"]),
            ("tooth_status", "دندان موردنظر هنوز وجود دارد یا قبلاً کشیده شده؟", ["هنوز وجود دارد", "کشیده شده", "بعضی کشیده شده‌اند", "نمی‌دانم"]),
            ("radiograph", "الان چه رادیوگرافی‌ای در اختیار دارید؟", ["OPG دارم", "CBCT دارم", "هر دو را دارم", "هیچ‌کدام"]),
            ("conditions", "بیماری زمینه‌ای مهم مثل دیابت، بیماری قلبی یا مصرف داروی خاص دارید؟", ["خیر", "بله", "مطمئن نیستم"]),
            ("medications", "داروی منظم مصرف می‌کنید؟ اگر بله نامش را بنویسید؛ اگر نه «خیر». بنویسید.", []),
            ("preferred_time", "چه زمانی برای مراجعه مناسب‌تر است؟", ["امروز یا فردا", "این هفته", "هفته آینده", "فعلاً فقط مشاوره می‌خواهم"]),
            ("patient_name", "نام و نام خانوادگی‌تان را بفرمایید.", []),
            ("patient_phone", "شماره موبایل برای هماهنگی را وارد کنید.", []),
        ],
    },
    "orthodontics": {
        "label": "ارتودنسی",
        "docs": ["عکس‌های داخل و خارج دهان در صورت وجود", "رادیوگرافی پانورامیک در صورت وجود", "سوابق درمان ارتودنسی قبلی"],
        "fields": [
            ("age", "سن بیمار چند سال است؟", []),
            ("reason", "دلیل اصلی مراجعه چیست؟", ["نامرتبی دندان‌ها", "مشکل فک", "فاصله بین دندان‌ها", "مشاوره"]),
            ("previous", "قبلاً ارتودنسی انجام شده؟", ["خیر", "بله"]),
            ("radiograph", "رادیوگرافی پانورامیک دارید؟", ["بله", "خیر"]),
            ("preferred_time", "چه زمانی برای مراجعه مناسب‌تر است؟", ["این هفته", "هفته آینده", "عجله ندارم"]),
            ("patient_name", "نام و نام خانوادگی‌تان را بفرمایید.", []),
            ("patient_phone", "شماره موبایل برای هماهنگی را وارد کنید.", []),
        ],
    },
    "general": {
        "label": "ویزیت",
        "docs": ["مدارک یا نتایج قبلی مرتبط در صورت وجود", "فهرست داروهای مصرفی در صورت مرتبط بودن"],
        "fields": [
            ("reason", "دلیل اصلی مراجعه‌تان چیست؟", []),
            ("preferred_time", "چه زمانی برای مراجعه مناسب‌تر است؟", ["امروز یا فردا", "این هفته", "هفته آینده"]),
            ("patient_name", "نام و نام خانوادگی‌تان را بفرمایید.", []),
            ("patient_phone", "شماره موبایل برای هماهنگی را وارد کنید.", []),
        ],
    },
}

SYNONYM_GROUPS = [
    {"قیمت", "هزینه", "تعرفه", "چند", "چنده", "مبلغ"},
    {"ایمپلنت", "کاشت", "کاشت دندان"},
    {"قسط", "اقساط", "قسطی", "پرداخت مرحله ای", "پرداخت مرحله‌ای"},
    {"بیمه", "طرف قرارداد", "قرارداد بیمه"},
    {"نوبت", "وقت", "ویزیت", "مراجعه"},
    {"آدرس", "کجاست", "موقعیت", "لوکیشن"},
    {"ساعت", "ساعات", "زمان کاری", "باز هستید"},
    {"زمان", "مدت", "طول", "طول میکشه", "چقدر طول"},
]


def create_drlinq_assistant_blueprint(data_root: str | Path) -> Blueprint:
    bp = Blueprint("drlinq_assistant", __name__, url_prefix="/alanoffer")
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

    def clean(v: Any, n: int = 800) -> str:
        return re.sub(r"\s+", " ", str(v or "")).strip()[:n]

    def norm(v: Any) -> str:
        s = clean(v, 1500).lower().replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
        s = re.sub(r"[^0-9a-z\u0600-\u06ff ]+", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    def tokens(v: Any) -> set[str]:
        stop = {"سلام", "لطفا", "لطفاً", "میخوام", "میخوام", "می خواهم", "میخواهم", "برای", "شما", "است", "هست", "رو", "را", "من", "یک", "چه", "چقدر", "میشه", "شود"}
        return {x for x in norm(v).split() if len(x) > 1 and x not in stop}

    def expanded_tokens(v: Any) -> set[str]:
        out = tokens(v)
        n = norm(v)
        for g in SYNONYM_GROUPS:
            if any(term in n for term in g):
                out |= {norm(term).replace(" ", "_") for term in g}
        return out

    def similarity(a: Any, b: Any) -> float:
        ta, tb = expanded_tokens(a), expanded_tokens(b)
        if not ta or not tb:
            return 0.0
        inter = len(ta & tb)
        return inter / max(1, min(len(ta), len(tb)))

    def jload(v: Any, default):
        try:
            x = json.loads(v or "")
            return x if isinstance(x, type(default)) else default
        except Exception:
            return default

    def safe_list(v: Any, limit: int = 40, item_len: int = 140):
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

    def slugify(v: Any) -> str:
        s = norm(v)
        s = re.sub(r"[^a-z0-9\u0600-\u06ff]+", "-", s).strip("-")
        return (s or "clinic")[:50]

    def init():
        with con() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS drlinq_assistant_clinics(
                    id TEXT PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    access_token TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    specialty TEXT NOT NULL DEFAULT 'general',
                    city TEXT NOT NULL DEFAULT '',
                    area TEXT NOT NULL DEFAULT '',
                    address_text TEXT NOT NULL DEFAULT '',
                    greeting TEXT NOT NULL DEFAULT '',
                    services_json TEXT NOT NULL DEFAULT '[]',
                    insurers_json TEXT NOT NULL DEFAULT '[]',
                    hours_text TEXT NOT NULL DEFAULT '',
                    payment_text TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS drlinq_assistant_knowledge(
                    id TEXT PRIMARY KEY,
                    clinic_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    service TEXT NOT NULL DEFAULT '',
                    use_count INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_assistant_knowledge_clinic ON drlinq_assistant_knowledge(clinic_id, active);
                CREATE TABLE IF NOT EXISTS drlinq_assistant_sessions(
                    id TEXT PRIMARY KEY,
                    clinic_id TEXT NOT NULL,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS drlinq_assistant_inquiries(
                    id TEXT PRIMARY KEY,
                    clinic_id TEXT NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL DEFAULT 'question',
                    question TEXT NOT NULL DEFAULT '',
                    answer TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'new',
                    context_json TEXT NOT NULL DEFAULT '{}',
                    summary TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_assistant_inquiries_clinic ON drlinq_assistant_inquiries(clinic_id, status, created_at);
                """
            )
            demo = c.execute("SELECT id FROM drlinq_assistant_clinics WHERE slug='demo-implant'").fetchone()
            if not demo:
                ts = now()
                cid = "asst_demo_implant"
                c.execute(
                    """INSERT INTO drlinq_assistant_clinics(
                    id,slug,access_token,name,category,specialty,city,area,address_text,greeting,services_json,insurers_json,hours_text,payment_text,active,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (cid,"demo-implant",secrets.token_urlsafe(24),"مرکز تخصصی ایمپلنت — نمونه دکتر لینک","مطب تخصصی","implant","اهواز","کیانپارس","","سلام، من دستیار هوشمند مرکز هستم. سؤال‌تان را به زبان خودتان بنویسید.",json.dumps(["ایمپلنت","جراحی ایمپلنت","روکش ایمپلنت"],ensure_ascii=False),json.dumps(["دانا","دی"],ensure_ascii=False),"شنبه تا چهارشنبه، عصرها","امکان پرداخت مرحله‌ای برای بعضی درمان‌ها پس از بررسی پرونده",1,ts,ts),
                )
                seeds = [
                    ("هزینه ایمپلنت چقدر است؟","هزینه ایمپلنت به برند، شرایط استخوان و نیاز یا عدم نیاز به درمان‌های جانبی بستگی دارد. مبلغ دقیق پس از بررسی رادیوگرافی و معاینه اعلام می‌شود."),
                    ("برای ایمپلنت چه مدارکی لازم است؟","اگر رادیوگرافی پانورامیک (OPG) دارید همراه داشته باشید. در بعضی موارد پزشک پس از بررسی، CBCT هم درخواست می‌کند. فهرست داروهای مصرفی و سوابق بیماری‌های مهم را نیز اعلام کنید."),
                    ("ایمپلنت قسطی دارید؟","برای بعضی پرونده‌ها امکان پرداخت مرحله‌ای وجود دارد و شرایط دقیق پس از بررسی طرح درمان اعلام می‌شود."),
                ]
                for q,a in seeds:
                    c.execute("INSERT INTO drlinq_assistant_knowledge(id,clinic_id,question,answer,service,use_count,active,created_at,updated_at) VALUES(?,?,?,?,?,0,1,?,?)",(f"kn_{secrets.token_hex(7)}",cid,q,a,"ایمپلنت",ts,ts))

    init()

    def clinic_auth(cid: str):
        token = clean(request.args.get("token") or request.headers.get("X-Assistant-Token"), 220)
        with con() as c:
            row = c.execute("SELECT * FROM drlinq_assistant_clinics WHERE id=? AND active=1", (clean(cid, 180),)).fetchone()
        if not row or not token or not secrets.compare_digest(token, row["access_token"]):
            return None
        return row

    def public_clinic(row):
        specialty = row["specialty"] if row["specialty"] in PACKAGES else "general"
        package = PACKAGES[specialty]
        return {
            "id": row["id"], "slug": row["slug"], "name": row["name"], "category": row["category"],
            "specialty": specialty, "city": row["city"], "area": row["area"], "addressText": row["address_text"],
            "greeting": row["greeting"], "services": jload(row["services_json"], []), "insurers": jload(row["insurers_json"], []),
            "hoursText": row["hours_text"], "paymentText": row["payment_text"], "requiredDocs": package["docs"],
        }

    def get_clinic_by_slug(slug: str):
        with con() as c:
            return c.execute("SELECT * FROM drlinq_assistant_clinics WHERE slug=? AND active=1", (clean(slug, 80),)).fetchone()

    def get_session(sid: str, clinic_id: str):
        if not sid:
            return None
        with con() as c:
            row = c.execute("SELECT * FROM drlinq_assistant_sessions WHERE id=? AND clinic_id=?", (clean(sid, 180), clinic_id)).fetchone()
        if not row:
            return None
        return jload(row["state_json"], {})

    def save_session(sid: str, clinic_id: str, state: dict):
        ts = now()
        with con() as c:
            row = c.execute("SELECT 1 FROM drlinq_assistant_sessions WHERE id=?", (sid,)).fetchone()
            if row:
                c.execute("UPDATE drlinq_assistant_sessions SET state_json=?,updated_at=? WHERE id=?", (json.dumps(state,ensure_ascii=False),ts,sid))
            else:
                c.execute("INSERT INTO drlinq_assistant_sessions(id,clinic_id,state_json,created_at,updated_at) VALUES(?,?,?,?,?)", (sid,clinic_id,json.dumps(state,ensure_ascii=False),ts,ts))

    def best_knowledge(clinic_id: str, text: str):
        with con() as c:
            rows = c.execute("SELECT * FROM drlinq_assistant_knowledge WHERE clinic_id=? AND active=1 ORDER BY updated_at DESC LIMIT 300", (clinic_id,)).fetchall()
        best, score = None, 0.0
        for row in rows:
            s = similarity(text, row["question"])
            if s > score:
                best, score = row, s
        if best and score >= 0.62:
            with con() as c:
                c.execute("UPDATE drlinq_assistant_knowledge SET use_count=use_count+1,updated_at=? WHERE id=?", (now(), best["id"]))
            return best, score
        return None, score

    def intent(text: str):
        n = norm(text)
        if any(x in n for x in ["بیمه", "طرف قرارداد"]): return "insurance"
        if any(x in n for x in ["ساعت", "کی باز", "زمان کاری"]): return "hours"
        if any(x in n for x in ["آدرس", "کجاست", "لوکیشن"]): return "address"
        if any(x in n for x in ["قسط", "اقساط", "پرداخت مرحله"]): return "payment"
        if any(x in n for x in ["نوبت", "وقت", "ویزیت", "میخوام بیام", "می خواهم بیایم", "شروع درمان"]): return "intake"
        if any(x in n for x in ["مدارک", "گرافی", "رادیوگرافی", "آزمایش", "عکس لازم"]): return "docs"
        return "question"

    def package_for(clinic):
        return PACKAGES.get(clinic["specialty"], PACKAGES["general"])

    def next_intake_question(clinic, state: dict):
        p = package_for(clinic)
        data = state.setdefault("intake", {})
        for key, q, options in p["fields"]:
            if not clean(data.get(key), 500):
                state["awaiting"] = key
                state["mode"] = "intake"
                return q, options
        state.pop("awaiting", None)
        state["mode"] = "complete"
        return None, []

    def intake_summary(clinic, state: dict) -> str:
        d = state.get("intake", {})
        label = package_for(clinic)["label"]
        parts = [f"خدمت: {label}"]
        labels = {"count":"تعداد","tooth_status":"وضعیت دندان","radiograph":"رادیوگرافی","conditions":"بیماری زمینه‌ای","medications":"دارو","preferred_time":"زمان مراجعه","patient_name":"نام بیمار","patient_phone":"تماس","age":"سن","reason":"علت مراجعه","previous":"سابقه درمان"}
        for k,v in d.items():
            if clean(v): parts.append(f"{labels.get(k,k)}: {clean(v,180)}")
        return " | ".join(parts)

    @bp.after_request
    def cors(resp):
        origin = request.headers.get("Origin", "")
        if origin in {"https://drlinq.ir", "https://www.drlinq.ir", "https://hajizadehmasoud5-ui.github.io"}:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Assistant-Token"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @bp.route("/api/assistant/<path:_p>", methods=["OPTIONS"])
    def options(_p): return ("", 204)

    @bp.get("/api/assistant/health")
    def health():
        return jsonify(ok=True, service="drlinq-adaptive-assistant", version=VERSION)

    @bp.post("/api/assistant/clinics/register")
    def register():
        b = request.get_json(silent=True) or {}
        name = clean(b.get("name"), 160)
        if not name: return jsonify(error="name_required"), 400
        specialty = clean(b.get("specialty"), 40) or "general"
        if specialty not in PACKAGES: specialty = "general"
        base = slugify(b.get("slug") or name)
        slug = base
        with con() as c:
            i = 2
            while c.execute("SELECT 1 FROM drlinq_assistant_clinics WHERE slug=?", (slug,)).fetchone():
                slug = f"{base[:42]}-{i}"; i += 1
            cid = f"asst_{int(time.time()*1000)}_{secrets.token_hex(5)}"
            token = secrets.token_urlsafe(24); ts = now()
            c.execute("""INSERT INTO drlinq_assistant_clinics(id,slug,access_token,name,category,specialty,city,area,address_text,greeting,services_json,insurers_json,hours_text,payment_text,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (cid,slug,token,name,clean(b.get("category"),100),specialty,clean(b.get("city"),80),clean(b.get("area"),100),clean(b.get("addressText"),300),clean(b.get("greeting"),300) or "سلام، من دستیار هوشمند مرکز هستم. سؤال‌تان را بنویسید.",json.dumps(safe_list(b.get("services")),ensure_ascii=False),json.dumps(safe_list(b.get("insurers")),ensure_ascii=False),clean(b.get("hoursText"),300),clean(b.get("paymentText"),300),1,ts,ts))
            for row in (b.get("knowledge") or []):
                if not isinstance(row, dict): continue
                q,a = clean(row.get("q"),300), clean(row.get("a"),1200)
                if q and a:
                    c.execute("INSERT INTO drlinq_assistant_knowledge(id,clinic_id,question,answer,service,use_count,active,created_at,updated_at) VALUES(?,?,?,?,?,0,1,?,?)", (f"kn_{secrets.token_hex(7)}",cid,q,a,clean(row.get("service"),120),ts,ts))
        return jsonify(ok=True, clinicId=cid, accessToken=token, slug=slug)

    @bp.get("/api/assistant/c/<slug>")
    def public(slug):
        clinic = get_clinic_by_slug(slug)
        if not clinic: return jsonify(error="not_found"), 404
        return jsonify(ok=True, clinic=public_clinic(clinic))

    @bp.post("/api/assistant/c/<slug>/message")
    def message(slug):
        clinic = get_clinic_by_slug(slug)
        if not clinic: return jsonify(error="not_found"), 404
        b = request.get_json(silent=True) or {}
        text = clean(b.get("text"), 1200)
        if not text: return jsonify(error="text_required"), 400
        sid = clean(b.get("sessionId"), 180) or f"as_{int(time.time()*1000)}_{secrets.token_hex(5)}"
        state = get_session(sid, clinic["id"]) or {}

        if state.get("mode") == "intake" and state.get("awaiting"):
            key = clean(state.get("awaiting"), 60)
            if key == "patient_phone":
                digits = re.sub(r"\D+", "", text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
                if len(digits) < 10:
                    return jsonify(ok=True, sessionId=sid, reply="شماره موبایل را کامل وارد کنید.", options=[], source="intake")
            state.setdefault("intake", {})[key] = text
            state.pop("awaiting", None)
            q, options = next_intake_question(clinic, state)
            if q:
                save_session(sid, clinic["id"], state)
                return jsonify(ok=True, sessionId=sid, reply=q, options=options, source="intake")
            summary = intake_summary(clinic, state)
            iid = f"aiq_{int(time.time()*1000)}_{secrets.token_hex(5)}"; ts = now()
            with con() as c:
                c.execute("INSERT INTO drlinq_assistant_inquiries(id,clinic_id,session_id,kind,question,answer,status,context_json,summary,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (iid,clinic["id"],sid,"previsit","","","ready",json.dumps(state.get("intake",{}),ensure_ascii=False),summary,ts,ts))
            save_session(sid, clinic["id"], state)
            return jsonify(ok=True, sessionId=sid, ready=True, reply="اطلاعات اولیه آماده شد و به مرکز ارسال شد. هنگام مراجعه، مدارک اصلی را هم همراه داشته باشید.", summary=summary, requiredDocs=package_for(clinic)["docs"], source="previsit")

        k, score = best_knowledge(clinic["id"], text)
        if k:
            save_session(sid, clinic["id"], state)
            return jsonify(ok=True, sessionId=sid, reply=k["answer"], options=[], source="clinic_memory", learned=True, confidence=round(score,2))

        it = intent(text)
        pc = public_clinic(clinic)
        if it == "insurance":
            reply = "بیمه‌های ثبت‌شده این مرکز: " + "، ".join(pc["insurers"]) if pc["insurers"] else "اطلاعات بیمه این مرکز هنوز ثبت نشده و باید توسط منشی بررسی شود."
            return jsonify(ok=True, sessionId=sid, reply=reply, options=[], source="clinic_profile")
        if it == "hours": return jsonify(ok=True, sessionId=sid, reply=pc["hoursText"] or "ساعات مراجعه هنوز ثبت نشده است.", options=[], source="clinic_profile")
        if it == "address": return jsonify(ok=True, sessionId=sid, reply=pc["addressText"] or f"{pc['city']}، {pc['area']}", options=[], source="clinic_profile")
        if it == "payment" and pc["paymentText"]: return jsonify(ok=True, sessionId=sid, reply=pc["paymentText"], options=[], source="clinic_profile")
        if it == "docs": return jsonify(ok=True, sessionId=sid, reply="برای این خدمت، بهتر است این موارد را در صورت وجود آماده کنید:", options=[], requiredDocs=package_for(clinic)["docs"], source="specialty_package")
        if it == "intake":
            state = {"mode":"intake","intake":{}}
            q, options = next_intake_question(clinic, state)
            save_session(sid, clinic["id"], state)
            return jsonify(ok=True, sessionId=sid, reply=q, options=options, source="intake", requiredDocs=package_for(clinic)["docs"])

        iid = f"aiq_{int(time.time()*1000)}_{secrets.token_hex(5)}"; ts = now()
        with con() as c:
            c.execute("INSERT INTO drlinq_assistant_inquiries(id,clinic_id,session_id,kind,question,answer,status,context_json,summary,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (iid,clinic["id"],sid,"question",text,"","new","{}","",ts,ts))
        save_session(sid, clinic["id"], state)
        return jsonify(ok=True, sessionId=sid, inquiryId=iid, needsHuman=True, reply="این سؤال هنوز پاسخ تأییدشده‌ای در حافظه مرکز ندارد. برای منشی ارسال شد؛ بعد از پاسخ، سؤال‌های مشابه را خود دستیار جواب می‌دهد.", options=[], source="human_handoff")

    @bp.get("/api/assistant/clinics/<cid>/dashboard")
    def dashboard(cid):
        clinic = clinic_auth(cid)
        if not clinic: return jsonify(error="unauthorized"), 401
        with con() as c:
            inqs = c.execute("SELECT * FROM drlinq_assistant_inquiries WHERE clinic_id=? ORDER BY created_at DESC LIMIT 150", (clinic["id"],)).fetchall()
            kn = c.execute("SELECT id,question,answer,service,use_count,created_at,updated_at FROM drlinq_assistant_knowledge WHERE clinic_id=? AND active=1 ORDER BY use_count DESC,updated_at DESC LIMIT 150", (clinic["id"],)).fetchall()
        return jsonify(ok=True, clinic=public_clinic(clinic), inquiries=[{"id":x["id"],"kind":x["kind"],"question":x["question"],"answer":x["answer"],"status":x["status"],"context":jload(x["context_json"],{}),"summary":x["summary"],"createdAt":x["created_at"]} for x in inqs], knowledge=[dict(x) for x in kn])

    @bp.post("/api/assistant/clinics/<cid>/inquiries/<iid>/answer")
    def answer_inquiry(cid, iid):
        clinic = clinic_auth(cid)
        if not clinic: return jsonify(error="unauthorized"), 401
        b = request.get_json(silent=True) or {}; answer = clean(b.get("answer"), 1600)
        if not answer: return jsonify(error="answer_required"), 400
        with con() as c:
            row = c.execute("SELECT * FROM drlinq_assistant_inquiries WHERE id=? AND clinic_id=?", (clean(iid,180), clinic["id"])).fetchone()
            if not row: return jsonify(error="not_found"), 404
            if row["kind"] == "question" and clean(row["question"]):
                existing = c.execute("SELECT id FROM drlinq_assistant_knowledge WHERE clinic_id=? AND question=? AND active=1", (clinic["id"], row["question"])).fetchone()
                if existing:
                    c.execute("UPDATE drlinq_assistant_knowledge SET answer=?,updated_at=? WHERE id=?", (answer,now(),existing["id"]))
                else:
                    c.execute("INSERT INTO drlinq_assistant_knowledge(id,clinic_id,question,answer,service,use_count,active,created_at,updated_at) VALUES(?,?,?,?,?,0,1,?,?)", (f"kn_{secrets.token_hex(7)}",clinic["id"],row["question"],answer,"",now(),now()))
            c.execute("UPDATE drlinq_assistant_inquiries SET answer=?,status='answered',updated_at=? WHERE id=?", (answer,now(),row["id"]))
        return jsonify(ok=True, learned=True, message="پاسخ ذخیره شد؛ سؤال‌های مشابه بعدی از حافظه مرکز پاسخ داده می‌شوند.")

    return bp
