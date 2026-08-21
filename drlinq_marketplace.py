from __future__ import annotations

import json
import re
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

VERSION = "0.6.0"


def create_drlinq_marketplace_blueprint(data_root: str | Path) -> Blueprint:
    bp = Blueprint("drlinq_marketplace", __name__, url_prefix="/alanoffer")
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

    def nid(prefix: str) -> str:
        return f"{prefix}_{int(time.time()*1000)}_{secrets.token_hex(8)}"

    def clean(v: Any, n: int = 500) -> str:
        return re.sub(r"\s+", " ", str(v or "")).strip()[:n]

    def norm(v: Any) -> str:
        return clean(v, 800).replace("ي", "ی").replace("ك", "ک").replace("‌", " ").lower()

    def digits(v: Any) -> str:
        return str(v or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))

    def money(v: Any) -> int:
        s = re.sub(r"[^0-9]", "", digits(v))
        try:
            return max(0, min(int(s or 0), 10_000_000_000))
        except Exception:
            return 0

    def pct(v: Any) -> int:
        s = re.sub(r"[^0-9]", "", digits(v))
        try:
            return max(0, min(int(s or 0), 100))
        except Exception:
            return 0

    def jload(v: Any, default):
        try:
            x = json.loads(v or "")
            return x if isinstance(x, type(default)) else default
        except Exception:
            return default

    def canon_service(v: Any) -> str:
        s = norm(v)
        groups = [
            ("ایمپلنت", ("ایمپلنت", "implant")),
            ("ارتودنسی", ("ارتودنسی", "orthodont")),
            ("درمان ریشه", ("عصب", "ریشه", "اندو", "endo")),
            ("روکش و پروتز", ("روکش", "پروتز", "زیرکون", "کراون", "crown")),
            ("ترمیم", ("ترمیم", "پرکرد", "پر کردن", "restor")),
            ("زیبایی", ("کامپوزیت", "ونیر", "لمینت", "زیبایی", "بلیچ")),
            ("جراحی و کشیدن", ("جراحی", "کشیدن", "دندان عقل", "extraction")),
            ("اطفال", ("اطفال", "کودک", "دندان شیری", "ped")),
        ]
        for name, keys in groups:
            if any(k in s for k in keys):
                return name
        return s[:120]

    def safe_provider_type(v: Any) -> str:
        s = norm(v)
        if s in {"general", "عمومی"}:
            return "general"
        if s in {"specialist", "متخصص"}:
            return "specialist"
        return "any"

    def clean_insurers(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        out, seen = [], set()
        for v in values:
            s = clean(v, 120)
            k = norm(s)
            if s and k not in seen:
                seen.add(k)
                out.append(s)
            if len(out) >= 5:
                break
        return out

    def clean_contracts(values: Any, service_fallback: str = "") -> list[dict[str, Any]]:
        if not isinstance(values, list):
            return []
        out = []
        for raw in values[:30]:
            if not isinstance(raw, dict):
                continue
            insurer = clean(raw.get("insurer"), 120)
            if not insurer:
                continue
            out.append({
                "insurer": insurer,
                "plan": clean(raw.get("plan"), 160),
                "service": clean(raw.get("service"), 120) or service_fallback,
                "franchise": pct(raw.get("franchise")),
                "patientShare": pct(raw.get("patientShare")),
                "validUntil": clean(raw.get("validUntil"), 40),
                "note": clean(raw.get("note"), 200),
            })
        return out

    def add_col(c: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
        cols = {row["name"] for row in c.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def init():
        with con() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS drlinq_requests(
                    id TEXT PRIMARY KEY,
                    service TEXT NOT NULL,
                    service_key TEXT NOT NULL,
                    city TEXT NOT NULL,
                    budget_max INTEGER NOT NULL DEFAULT 0,
                    priorities_json TEXT NOT NULL DEFAULT '[]',
                    wait TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'matching',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_drlinq_requests_match ON drlinq_requests(city, service_key, status, created_at);
                CREATE TABLE IF NOT EXISTS drlinq_providers(
                    id TEXT PRIMARY KEY,
                    access_token TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    city TEXT NOT NULL,
                    service TEXT NOT NULL,
                    service_key TEXT NOT NULL,
                    price_min INTEGER NOT NULL DEFAULT 0,
                    price_max INTEGER NOT NULL DEFAULT 0,
                    availability TEXT NOT NULL DEFAULT '',
                    features_json TEXT NOT NULL DEFAULT '[]',
                    offer_text TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_drlinq_providers_match ON drlinq_providers(city, service_key, active);
                CREATE TABLE IF NOT EXISTS drlinq_matches(
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'candidate',
                    offered_price INTEGER NOT NULL DEFAULT 0,
                    availability TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(request_id, provider_id)
                );
                CREATE INDEX IF NOT EXISTS idx_drlinq_matches_provider ON drlinq_matches(provider_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_drlinq_matches_request ON drlinq_matches(request_id, status, updated_at);
            """)
            add_col(c, "drlinq_requests", "provider_type", "TEXT NOT NULL DEFAULT 'any'")
            add_col(c, "drlinq_requests", "area", "TEXT NOT NULL DEFAULT ''")
            add_col(c, "drlinq_requests", "insurers_json", "TEXT NOT NULL DEFAULT '[]'")
            add_col(c, "drlinq_requests", "insurance_plan", "TEXT NOT NULL DEFAULT ''")
            add_col(c, "drlinq_providers", "provider_type", "TEXT NOT NULL DEFAULT 'specialist'")
            add_col(c, "drlinq_providers", "area", "TEXT NOT NULL DEFAULT ''")
            add_col(c, "drlinq_providers", "insurance_json", "TEXT NOT NULL DEFAULT '[]'")

    init()

    def insurance_matches(req_row, prv_row) -> list[dict[str, Any]]:
        selected = [norm(x) for x in jload(req_row["insurers_json"], []) if norm(x)]
        if not selected:
            return []
        matched = []
        for raw in jload(prv_row["insurance_json"], []):
            if not isinstance(raw, dict) or norm(raw.get("insurer")) not in selected:
                continue
            row = dict(raw)
            req_plan, plan = norm(req_row["insurance_plan"]), norm(raw.get("plan"))
            row["planMatch"] = bool(req_plan and plan and (req_plan in plan or plan in req_plan))
            matched.append(row)
        matched.sort(key=lambda x: (0 if x.get("planMatch") else 1, int(x.get("patientShare") or 0)))
        return matched

    def compatible(req_row, prv_row) -> bool:
        if norm(req_row["city"]) != norm(prv_row["city"]):
            return False
        if clean(req_row["service_key"]) != clean(prv_row["service_key"]):
            return False
        wanted = clean(req_row["provider_type"], 30) or "any"
        have = clean(prv_row["provider_type"], 30) or "specialist"
        if wanted in {"general", "specialist"} and have != wanted:
            return False
        budget, pmin = int(req_row["budget_max"] or 0), int(prv_row["price_min"] or 0)
        if budget and pmin and pmin > budget:
            return False
        if jload(req_row["insurers_json"], []) and not insurance_matches(req_row, prv_row):
            return False
        return True

    def match_score(req_row, prv_row) -> int:
        score = 50
        req_area, prv_area = norm(req_row["area"]), norm(prv_row["area"])
        if req_area and prv_area and (req_area in prv_area or prv_area in req_area):
            score += 15
        priorities = [norm(x) for x in jload(req_row["priorities_json"], [])]
        if any("سریع" in x or "نوبت" in x for x in priorities) and clean(prv_row["availability"]):
            score += 10
        if any("هزینه" in x or "به صرفه" in x or "به‌صرفه" in x for x in priorities):
            if int(prv_row["price_min"] or 0):
                score += 5
            if clean(prv_row["offer_text"]):
                score += 5
        if insurance_matches(req_row, prv_row):
            score += 15
        return min(score, 100)

    def ensure_request_matches(request_id: str) -> int:
        with con() as c:
            rr = c.execute("SELECT * FROM drlinq_requests WHERE id=?", (request_id,)).fetchone()
            if not rr:
                return 0
            providers = c.execute("SELECT * FROM drlinq_providers WHERE active=1 AND service_key=?", (rr["service_key"],)).fetchall()
            count, ts = 0, now()
            for p in providers:
                if not compatible(rr, p):
                    continue
                old = c.execute("SELECT id FROM drlinq_matches WHERE request_id=? AND provider_id=?", (request_id, p["id"])).fetchone()
                if old:
                    continue
                c.execute("INSERT INTO drlinq_matches(id,request_id,provider_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?)", (nid("mt"), request_id, p["id"], "candidate", ts, ts))
                count += 1
            return count

    def ensure_provider_matches(provider_id: str) -> int:
        with con() as c:
            pp = c.execute("SELECT * FROM drlinq_providers WHERE id=?", (provider_id,)).fetchone()
            if not pp:
                return 0
            rows = c.execute("SELECT * FROM drlinq_requests WHERE service_key=? AND status IN ('matching','provider_interested') ORDER BY created_at DESC LIMIT 100", (pp["service_key"],)).fetchall()
            count, ts = 0, now()
            for rr in rows:
                if not compatible(rr, pp):
                    continue
                old = c.execute("SELECT id FROM drlinq_matches WHERE request_id=? AND provider_id=?", (rr["id"], provider_id)).fetchone()
                if old:
                    continue
                c.execute("INSERT INTO drlinq_matches(id,request_id,provider_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?)", (nid("mt"), rr["id"], provider_id, "candidate", ts, ts))
                count += 1
            return count

    def provider_auth(pid: str):
        token = clean(request.args.get("token") or request.headers.get("X-Provider-Token"), 200)
        with con() as c:
            p = c.execute("SELECT * FROM drlinq_providers WHERE id=?", (clean(pid, 160),)).fetchone()
        if not p or not token or not secrets.compare_digest(token, p["access_token"]):
            return None
        return p

    @bp.after_request
    def cors(resp):
        origin = request.headers.get("Origin", "")
        if origin in {"https://drlinq.ir", "https://www.drlinq.ir", "https://hajizadehmasoud5-ui.github.io"}:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Provider-Token"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @bp.route("/api/v2/<path:_p>", methods=["OPTIONS"])
    def options(_p):
        return ("", 204)

    @bp.get("/api/v2/health")
    def health():
        with con() as c:
            rq = c.execute("SELECT COUNT(*) n FROM drlinq_requests").fetchone()["n"]
            pv = c.execute("SELECT COUNT(*) n FROM drlinq_providers WHERE active=1").fetchone()["n"]
            mt = c.execute("SELECT COUNT(*) n FROM drlinq_matches").fetchone()["n"]
        return jsonify(ok=True, service="drlinq-dental-marketplace", version=VERSION, requests=rq, providers=pv, matches=mt)

    @bp.post("/api/v2/requests")
    def create_request():
        b = request.get_json(silent=True) or {}
        service, city = clean(b.get("service"), 120), clean(b.get("city"), 80)
        if not service or not city:
            return jsonify(error="service_and_city_required"), 400
        priorities = b.get("priorities") if isinstance(b.get("priorities"), list) else []
        priorities = [clean(x, 80) for x in priorities if clean(x, 80)][:3]
        insurers = clean_insurers(b.get("insurers"))
        rid, ts = nid("req2"), now()
        with con() as c:
            c.execute("""
                INSERT INTO drlinq_requests(id,service,service_key,city,budget_max,priorities_json,wait,note,status,created_at,updated_at,provider_type,area,insurers_json,insurance_plan)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (rid, service, canon_service(service), city, money(b.get("budgetMax")), json.dumps(priorities, ensure_ascii=False), clean(b.get("wait"),80), clean(b.get("note"),500), "matching", ts, ts, safe_provider_type(b.get("providerType")), clean(b.get("area"),100), json.dumps(insurers, ensure_ascii=False), clean(b.get("insurancePlan"),160)))
        return jsonify(ok=True, requestId=rid, status="matching", matchedProviders=ensure_request_matches(rid))

    @bp.get("/api/v2/requests/<rid>")
    def request_dashboard(rid):
        rrid = clean(rid, 180)
        ensure_request_matches(rrid)
        with con() as c:
            r = c.execute("SELECT * FROM drlinq_requests WHERE id=?", (rrid,)).fetchone()
            if not r:
                return jsonify(error="not_found"), 404
            offers = c.execute("""
                SELECT m.provider_id,m.status,m.offered_price,m.availability,m.note,m.updated_at,
                       p.name,p.city,p.area,p.service,p.provider_type,p.price_min,p.price_max,p.features_json,p.offer_text,p.insurance_json
                FROM drlinq_matches m JOIN drlinq_providers p ON p.id=m.provider_id
                WHERE m.request_id=? AND m.status IN ('interested','selected')
                ORDER BY CASE WHEN m.status='selected' THEN 0 ELSE 1 END, m.updated_at DESC
            """, (rrid,)).fetchall()
            pending = c.execute("SELECT COUNT(*) n FROM drlinq_matches WHERE request_id=? AND status='candidate'", (rrid,)).fetchone()["n"]
        req = {"id":r["id"],"service":r["service"],"city":r["city"],"area":r["area"],"providerType":r["provider_type"],"budgetMax":r["budget_max"],"priorities":jload(r["priorities_json"],[]),"wait":r["wait"],"note":r["note"],"insurers":jload(r["insurers_json"],[]),"insurancePlan":r["insurance_plan"],"status":r["status"]}
        selected = [norm(i) for i in req["insurers"] if norm(i)]
        out = []
        for x in offers:
            ins = [c for c in jload(x["insurance_json"], []) if isinstance(c,dict) and (not selected or norm(c.get("insurer")) in selected)]
            ins.sort(key=lambda z: int(z.get("patientShare") or 0))
            out.append({"providerId":x["provider_id"],"status":x["status"],"providerName":x["name"],"providerType":x["provider_type"],"service":x["service"],"city":x["city"],"area":x["area"],"providerPriceMin":x["price_min"],"providerPriceMax":x["price_max"],"offeredPrice":x["offered_price"],"availability":x["availability"],"features":jload(x["features_json"],[]),"offerText":x["offer_text"],"insuranceMatches":ins,"note":x["note"]})
        return jsonify(ok=True, request=req, pendingMatches=pending, offers=out)

    @bp.post("/api/v2/requests/<rid>/select")
    def select_provider(rid):
        b = request.get_json(silent=True) or {}
        rrid, pid = clean(rid,180), clean(b.get("providerId"),180)
        if not pid:
            return jsonify(error="provider_required"), 400
        ts = now()
        with con() as c:
            m = c.execute("SELECT status FROM drlinq_matches WHERE request_id=? AND provider_id=?", (rrid,pid)).fetchone()
            if not m or m["status"] not in {"interested","selected"}:
                return jsonify(error="offer_not_available"), 409
            c.execute("UPDATE drlinq_matches SET status='selected',updated_at=? WHERE request_id=? AND provider_id=?", (ts,rrid,pid))
            c.execute("UPDATE drlinq_requests SET status='selected',updated_at=? WHERE id=?", (ts,rrid))
        return jsonify(ok=True,status="selected",providerId=pid)

    @bp.post("/api/v2/providers/register")
    def register_provider():
        b = request.get_json(silent=True) or {}
        name, city, service = clean(b.get("name"),160), clean(b.get("city"),80), clean(b.get("service"),120)
        if not name or not city or not service:
            return jsonify(error="name_city_service_required"), 400
        pmin, pmax = money(b.get("priceMin")), money(b.get("priceMax"))
        if pmin and pmax and pmax < pmin:
            pmin, pmax = pmax, pmin
        features = b.get("features") if isinstance(b.get("features"),list) else []
        features = [clean(x,80) for x in features if clean(x,80)][:8]
        provider_type = safe_provider_type(b.get("providerType"))
        if provider_type == "any":
            provider_type = "specialist"
        pid, tok, ts = nid("prv2"), secrets.token_urlsafe(24), now()
        contracts = clean_contracts(b.get("insuranceContracts"), service)
        with con() as c:
            c.execute("""
                INSERT INTO drlinq_providers(id,access_token,name,city,service,service_key,price_min,price_max,availability,features_json,offer_text,active,created_at,updated_at,provider_type,area,insurance_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (pid,tok,name,city,service,canon_service(service),pmin,pmax,clean(b.get("availability"),100),json.dumps(features,ensure_ascii=False),clean(b.get("offerText"),300),1,ts,ts,provider_type,clean(b.get("area"),100),json.dumps(contracts,ensure_ascii=False)))
        return jsonify(ok=True,providerId=pid,accessToken=tok,matchedRequests=ensure_provider_matches(pid))

    @bp.post("/api/v2/providers/<pid>/profile")
    def update_provider_profile(pid):
        p = provider_auth(pid)
        if not p:
            return jsonify(error="unauthorized"), 401
        b = request.get_json(silent=True) or {}
        name = clean(b.get("name"),160) or p["name"]
        city = clean(b.get("city"),80) or p["city"]
        service = clean(b.get("service"),120) or p["service"]
        pmin = money(b.get("priceMin")) if "priceMin" in b else int(p["price_min"] or 0)
        pmax = money(b.get("priceMax")) if "priceMax" in b else int(p["price_max"] or 0)
        if pmin and pmax and pmax < pmin:
            pmin, pmax = pmax, pmin
        features = [clean(x,80) for x in b.get("features",[]) if clean(x,80)][:8] if isinstance(b.get("features"),list) else jload(p["features_json"],[])
        contracts = clean_contracts(b.get("insuranceContracts"), service) if isinstance(b.get("insuranceContracts"),list) else jload(p["insurance_json"],[])
        provider_type = safe_provider_type(b.get("providerType")) if "providerType" in b else clean(p["provider_type"],30)
        if provider_type == "any":
            provider_type = "specialist"
        ts = now()
        with con() as c:
            c.execute("""
                UPDATE drlinq_providers SET name=?,city=?,service=?,service_key=?,price_min=?,price_max=?,availability=?,features_json=?,offer_text=?,provider_type=?,area=?,insurance_json=?,updated_at=? WHERE id=?
            """, (name,city,service,canon_service(service),pmin,pmax,clean(b.get("availability"),100) if "availability" in b else p["availability"],json.dumps(features,ensure_ascii=False),clean(b.get("offerText"),300) if "offerText" in b else p["offer_text"],provider_type,clean(b.get("area"),100) if "area" in b else p["area"],json.dumps(contracts,ensure_ascii=False),ts,p["id"]))
        ensure_provider_matches(p["id"])
        return jsonify(ok=True,providerId=p["id"],saved=True)

    @bp.get("/api/v2/providers/<pid>/dashboard")
    def provider_dashboard(pid):
        p = provider_auth(pid)
        if not p:
            return jsonify(error="unauthorized"), 401
        ensure_provider_matches(p["id"])
        with con() as c:
            rows = c.execute("""
                SELECT m.request_id,m.status,m.offered_price,m.availability,m.note,
                       r.service,r.city,r.area,r.provider_type,r.budget_max,r.priorities_json,r.wait,r.note AS request_note,r.status AS request_status,r.created_at,r.insurers_json,r.insurance_plan
                FROM drlinq_matches m JOIN drlinq_requests r ON r.id=m.request_id
                WHERE m.provider_id=? AND m.status IN ('candidate','interested','selected') ORDER BY r.created_at DESC LIMIT 100
            """, (p["id"],)).fetchall()
        reqs = [{"requestId":x["request_id"],"matchStatus":x["status"],"offeredPrice":x["offered_price"],"offerAvailability":x["availability"],"offerNote":x["note"],"service":x["service"],"city":x["city"],"area":x["area"],"providerType":x["provider_type"],"budgetMax":x["budget_max"],"priorities":jload(x["priorities_json"],[]),"wait":x["wait"],"note":x["request_note"],"insurers":jload(x["insurers_json"],[]),"insurancePlan":x["insurance_plan"],"requestStatus":x["request_status"],"score":match_score(x,p)} for x in rows]
        provider = {"id":p["id"],"name":p["name"],"city":p["city"],"area":p["area"],"providerType":p["provider_type"],"service":p["service"],"priceMin":p["price_min"],"priceMax":p["price_max"],"availability":p["availability"],"features":jload(p["features_json"],[]),"offerText":p["offer_text"],"insuranceContracts":jload(p["insurance_json"],[])}
        return jsonify(ok=True,provider=provider,requests=reqs)

    @bp.post("/api/v2/providers/<pid>/requests/<rid>/offer")
    def provider_offer(pid, rid):
        p = provider_auth(pid)
        if not p:
            return jsonify(error="unauthorized"), 401
        b = request.get_json(silent=True) or {}
        action = clean(b.get("action"),30)
        if action not in {"interested","rejected"}:
            return jsonify(error="invalid_action"), 400
        rrid, ts = clean(rid,180), now()
        with con() as c:
            m = c.execute("SELECT id FROM drlinq_matches WHERE request_id=? AND provider_id=?", (rrid,p["id"])).fetchone()
            if not m:
                return jsonify(error="match_not_found"), 404
            c.execute("UPDATE drlinq_matches SET status=?,offered_price=?,availability=?,note=?,updated_at=? WHERE request_id=? AND provider_id=?", (action,money(b.get("offeredPrice")),clean(b.get("availability"),100) or p["availability"],clean(b.get("note"),500),ts,rrid,p["id"]))
            if action == "interested":
                c.execute("UPDATE drlinq_requests SET status='provider_interested',updated_at=? WHERE id=? AND status='matching'", (ts,rrid))
        return jsonify(ok=True,status=action)

    return bp
