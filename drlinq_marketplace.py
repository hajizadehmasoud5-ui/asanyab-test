from __future__ import annotations

import json
import re
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

VERSION = "0.5.0"


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
        return (
            clean(v, 800)
            .replace("ي", "ی")
            .replace("ك", "ک")
            .replace("‌", " ")
            .lower()
        )

    def digits(v: Any) -> str:
        return str(v or "").translate(
            str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        )

    def money(v: Any) -> int:
        s = re.sub(r"[^0-9]", "", digits(v))
        try:
            return max(0, min(int(s or 0), 10_000_000_000))
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

    def init():
        with con() as c:
            c.executescript(
                """
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
                CREATE INDEX IF NOT EXISTS idx_drlinq_requests_match
                    ON drlinq_requests(city, service_key, status, created_at);

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
                CREATE INDEX IF NOT EXISTS idx_drlinq_providers_match
                    ON drlinq_providers(city, service_key, active);

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
                CREATE INDEX IF NOT EXISTS idx_drlinq_matches_provider
                    ON drlinq_matches(provider_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_drlinq_matches_request
                    ON drlinq_matches(request_id, status, updated_at);
                """
            )

    init()

    def compatible(req_row, prv_row) -> bool:
        if norm(req_row["city"]) != norm(prv_row["city"]):
            return False
        if clean(req_row["service_key"]) != clean(prv_row["service_key"]):
            return False
        budget = int(req_row["budget_max"] or 0)
        pmin = int(prv_row["price_min"] or 0)
        if budget and pmin and pmin > budget:
            return False
        return True

    def ensure_request_matches(request_id: str) -> int:
        with con() as c:
            rr = c.execute("SELECT * FROM drlinq_requests WHERE id=?", (request_id,)).fetchone()
            if not rr:
                return 0
            providers = c.execute(
                "SELECT * FROM drlinq_providers WHERE active=1 AND service_key=?",
                (rr["service_key"],),
            ).fetchall()
            count = 0
            ts = now()
            for p in providers:
                if not compatible(rr, p):
                    continue
                old = c.execute(
                    "SELECT id FROM drlinq_matches WHERE request_id=? AND provider_id=?",
                    (request_id, p["id"]),
                ).fetchone()
                if old:
                    continue
                c.execute(
                    "INSERT INTO drlinq_matches(id,request_id,provider_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (nid("mt"), request_id, p["id"], "candidate", ts, ts),
                )
                count += 1
            return count

    def ensure_provider_matches(provider_id: str) -> int:
        with con() as c:
            pp = c.execute("SELECT * FROM drlinq_providers WHERE id=?", (provider_id,)).fetchone()
            if not pp:
                return 0
            requests = c.execute(
                "SELECT * FROM drlinq_requests WHERE service_key=? AND status IN ('matching','provider_interested') ORDER BY created_at DESC LIMIT 100",
                (pp["service_key"],),
            ).fetchall()
            count = 0
            ts = now()
            for rr in requests:
                if not compatible(rr, pp):
                    continue
                old = c.execute(
                    "SELECT id FROM drlinq_matches WHERE request_id=? AND provider_id=?",
                    (rr["id"], provider_id),
                ).fetchone()
                if old:
                    continue
                c.execute(
                    "INSERT INTO drlinq_matches(id,request_id,provider_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (nid("mt"), rr["id"], provider_id, "candidate", ts, ts),
                )
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
        if origin in {
            "https://drlinq.ir",
            "https://www.drlinq.ir",
            "https://hajizadehmasoud5-ui.github.io",
        }:
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
        service = clean(b.get("service"), 120)
        city = clean(b.get("city"), 80)
        if not service or not city:
            return jsonify(error="service_and_city_required"), 400
        priorities = b.get("priorities") if isinstance(b.get("priorities"), list) else []
        priorities = [clean(x, 80) for x in priorities if clean(x, 80)][:2]
        rid = nid("req2")
        ts = now()
        with con() as c:
            c.execute(
                "INSERT INTO drlinq_requests(id,service,service_key,city,budget_max,priorities_json,wait,note,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rid,
                    service,
                    canon_service(service),
                    city,
                    money(b.get("budgetMax")),
                    json.dumps(priorities, ensure_ascii=False),
                    clean(b.get("wait"), 80),
                    clean(b.get("note"), 500),
                    "matching",
                    ts,
                    ts,
                ),
            )
        matched = ensure_request_matches(rid)
        return jsonify(ok=True, requestId=rid, status="matching", matchedProviders=matched)

    @bp.get("/api/v2/requests/<rid>")
    def request_dashboard(rid):
        rrid = clean(rid, 180)
        ensure_request_matches(rrid)
        with con() as c:
            r = c.execute("SELECT * FROM drlinq_requests WHERE id=?", (rrid,)).fetchone()
            if not r:
                return jsonify(error="not_found"), 404
            offers = c.execute(
                """
                SELECT m.provider_id,m.status,m.offered_price,m.availability,m.note,m.updated_at,
                       p.name,p.city,p.service,p.price_min,p.price_max,p.features_json,p.offer_text
                FROM drlinq_matches m
                JOIN drlinq_providers p ON p.id=m.provider_id
                WHERE m.request_id=? AND m.status IN ('interested','selected')
                ORDER BY CASE WHEN m.status='selected' THEN 0 ELSE 1 END, m.updated_at DESC
                """,
                (rrid,),
            ).fetchall()
            pending = c.execute(
                "SELECT COUNT(*) n FROM drlinq_matches WHERE request_id=? AND status='candidate'",
                (rrid,),
            ).fetchone()["n"]
        return jsonify(
            ok=True,
            request={
                "id": r["id"],
                "service": r["service"],
                "city": r["city"],
                "budgetMax": r["budget_max"],
                "priorities": jload(r["priorities_json"], []),
                "wait": r["wait"],
                "note": r["note"],
                "status": r["status"],
            },
            pendingMatches=pending,
            offers=[
                {
                    "providerId": x["provider_id"],
                    "status": x["status"],
                    "providerName": x["name"],
                    "service": x["service"],
                    "city": x["city"],
                    "providerPriceMin": x["price_min"],
                    "providerPriceMax": x["price_max"],
                    "offeredPrice": x["offered_price"],
                    "availability": x["availability"],
                    "features": jload(x["features_json"], []),
                    "offerText": x["offer_text"],
                    "note": x["note"],
                }
                for x in offers
            ],
        )

    @bp.post("/api/v2/requests/<rid>/select")
    def select_provider(rid):
        b = request.get_json(silent=True) or {}
        rrid = clean(rid, 180)
        pid = clean(b.get("providerId"), 180)
        if not pid:
            return jsonify(error="provider_required"), 400
        ts = now()
        with con() as c:
            m = c.execute(
                "SELECT status FROM drlinq_matches WHERE request_id=? AND provider_id=?",
                (rrid, pid),
            ).fetchone()
            if not m or m["status"] not in {"interested", "selected"}:
                return jsonify(error="offer_not_available"), 409
            c.execute(
                "UPDATE drlinq_matches SET status='selected',updated_at=? WHERE request_id=? AND provider_id=?",
                (ts, rrid, pid),
            )
            c.execute(
                "UPDATE drlinq_requests SET status='selected',updated_at=? WHERE id=?",
                (ts, rrid),
            )
        return jsonify(ok=True, status="selected", providerId=pid)

    @bp.post("/api/v2/providers/register")
    def register_provider():
        b = request.get_json(silent=True) or {}
        name = clean(b.get("name"), 160)
        city = clean(b.get("city"), 80)
        service = clean(b.get("service"), 120)
        if not name or not city or not service:
            return jsonify(error="name_city_service_required"), 400
        pmin = money(b.get("priceMin"))
        pmax = money(b.get("priceMax"))
        if pmin and pmax and pmax < pmin:
            pmin, pmax = pmax, pmin
        features = b.get("features") if isinstance(b.get("features"), list) else []
        features = [clean(x, 80) for x in features if clean(x, 80)][:5]
        pid = nid("prv2")
        tok = secrets.token_urlsafe(24)
        ts = now()
        with con() as c:
            c.execute(
                "INSERT INTO drlinq_providers(id,access_token,name,city,service,service_key,price_min,price_max,availability,features_json,offer_text,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    pid,
                    tok,
                    name,
                    city,
                    service,
                    canon_service(service),
                    pmin,
                    pmax,
                    clean(b.get("availability"), 100),
                    json.dumps(features, ensure_ascii=False),
                    clean(b.get("offerText"), 300),
                    1,
                    ts,
                    ts,
                ),
            )
        matched = ensure_provider_matches(pid)
        return jsonify(ok=True, providerId=pid, accessToken=tok, matchedRequests=matched)

    @bp.get("/api/v2/providers/<pid>/dashboard")
    def provider_dashboard(pid):
        p = provider_auth(pid)
        if not p:
            return jsonify(error="unauthorized"), 401
        ensure_provider_matches(p["id"])
        with con() as c:
            rows = c.execute(
                """
                SELECT m.request_id,m.status,m.offered_price,m.availability,m.note,
                       r.service,r.city,r.budget_max,r.priorities_json,r.wait,r.note AS request_note,r.status AS request_status,r.created_at
                FROM drlinq_matches m
                JOIN drlinq_requests r ON r.id=m.request_id
                WHERE m.provider_id=? AND m.status IN ('candidate','interested','selected')
                ORDER BY r.created_at DESC LIMIT 100
                """,
                (p["id"],),
            ).fetchall()
        return jsonify(
            ok=True,
            provider={
                "id": p["id"],
                "name": p["name"],
                "city": p["city"],
                "service": p["service"],
                "priceMin": p["price_min"],
                "priceMax": p["price_max"],
                "availability": p["availability"],
                "features": jload(p["features_json"], []),
                "offerText": p["offer_text"],
            },
            requests=[
                {
                    "requestId": x["request_id"],
                    "matchStatus": x["status"],
                    "offeredPrice": x["offered_price"],
                    "offerAvailability": x["availability"],
                    "offerNote": x["note"],
                    "service": x["service"],
                    "city": x["city"],
                    "budgetMax": x["budget_max"],
                    "priorities": jload(x["priorities_json"], []),
                    "wait": x["wait"],
                    "note": x["request_note"],
                    "requestStatus": x["request_status"],
                }
                for x in rows
            ],
        )

    @bp.post("/api/v2/providers/<pid>/requests/<rid>/offer")
    def provider_offer(pid, rid):
        p = provider_auth(pid)
        if not p:
            return jsonify(error="unauthorized"), 401
        b = request.get_json(silent=True) or {}
        action = clean(b.get("action"), 30)
        if action not in {"interested", "rejected"}:
            return jsonify(error="invalid_action"), 400
        rrid = clean(rid, 180)
        ts = now()
        with con() as c:
            m = c.execute(
                "SELECT id FROM drlinq_matches WHERE request_id=? AND provider_id=?",
                (rrid, p["id"]),
            ).fetchone()
            if not m:
                return jsonify(error="match_not_found"), 404
            c.execute(
                "UPDATE drlinq_matches SET status=?,offered_price=?,availability=?,note=?,updated_at=? WHERE request_id=? AND provider_id=?",
                (
                    action,
                    money(b.get("offeredPrice")),
                    clean(b.get("availability"), 100) or p["availability"],
                    clean(b.get("note"), 500),
                    ts,
                    rrid,
                    p["id"],
                ),
            )
            if action == "interested":
                c.execute(
                    "UPDATE drlinq_requests SET status='provider_interested',updated_at=? WHERE id=? AND status='matching'",
                    (ts, rrid),
                )
        return jsonify(ok=True, status=action)

    return bp
