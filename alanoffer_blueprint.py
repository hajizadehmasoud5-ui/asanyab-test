from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import secrets
import time
from pathlib import Path
from typing import Any

import requests
from flask import Blueprint, jsonify, request, redirect, make_response, render_template_string


def create_alanoffer_blueprint(data_root: str | Path) -> Blueprint:
    """Create AlanOffer API blueprint for the existing Cloudiva Flask service.

    Mounts under /alanoffer and keeps the old app/routes untouched.
    Uses stdlib sqlite3 + existing requests/Flask dependencies only.
    """
    bp = Blueprint("alanoffer", __name__, url_prefix="/alanoffer")
    root = Path(data_root) / "alanoffer"
    root.mkdir(parents=True, exist_ok=True)
    db_path = Path(os.environ.get("ALANOFFER_DB_PATH", str(root / "alanoffer.db")))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    cors_origins = {
        x.strip()
        for x in os.environ.get(
            "ALANOFFER_CORS_ORIGINS",
            "https://hajizadehmasoud5-ui.github.io",
        ).split(",")
        if x.strip()
    }
    token_file = root / "admin_token.txt"
    env_admin_token = os.environ.get("ALANOFFER_ADMIN_TOKEN", "").strip()
    if env_admin_token:
        admin_token = env_admin_token
    elif token_file.exists():
        admin_token = token_file.read_text(encoding="utf-8").strip()
    else:
        admin_token = secrets.token_urlsafe(32)
        token_file.write_text(admin_token, encoding="utf-8")
        try:
            token_file.chmod(0o600)
        except Exception:
            pass

    # Optional one-time device pairing secret. Keep it only in the service environment.
    setup_secret = os.environ.get("ALANOFFER_ADMIN_SETUP_SECRET", "").strip()
    setup_used_file = root / "admin_setup_used.txt"
    admin_cookie = "alanoffer_admin"
    lock = threading.Lock()
    last_sync: dict[str, float] = {}

    ahvaz_bbox = "31.15,48.50,31.47,48.88"
    overpass_endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]

    osm_catalog: dict[str, dict[str, list[str]]] = {
        "food": {
            "restaurant": ['["amenity"="restaurant"]'],
            "fastfood": ['["amenity"="fast_food"]'],
            "cafe": ['["amenity"="cafe"]'],
            "juice": ['["amenity"="ice_cream"]', '["shop"="ice_cream"]'],
            "catering": ['["amenity"="food_court"]'],
        },
        "grocery": {
            "produce": ['["shop"="greengrocer"]'],
            "bakery": ['["shop"="bakery"]'],
            "pastry": ['["shop"="confectionery"]', '["shop"="pastry"]'],
            "protein": ['["shop"="butcher"]', '["shop"="seafood"]'],
            "dairy": ['["shop"="dairy"]'],
            "supermarket": ['["shop"="supermarket"]', '["shop"="convenience"]'],
            "nuts": ['["shop"="nuts"]'],
        },
        "health": {
            "dentist": ['["amenity"="dentist"]', '["healthcare"="dentist"]'],
            "dental_specialist": ['["healthcare"="dentist"]'],
            "general_doctor": ['["amenity"="doctors"]', '["healthcare"="doctor"]'],
            "specialist_doctor": ['["healthcare"="doctor"]'],
            "clinic": ['["amenity"="clinic"]', '["healthcare"="clinic"]'],
            "hospital": ['["amenity"="hospital"]'],
            "pharmacy": ['["amenity"="pharmacy"]'],
            "lab": ['["healthcare"="laboratory"]'],
            "imaging": ['["healthcare"="diagnostics"]'],
            "physio": ['["healthcare"="physiotherapist"]'],
            "psychology": ['["healthcare"="psychotherapist"]', '["office"="psychologist"]'],
            "optometry": ['["shop"="optician"]'],
            "hearing": ['["healthcare"="audiologist"]'],
        },
        "beauty": {
            "barber": ['["shop"="hairdresser"]'],
            "salon": ['["shop"="hairdresser"]'],
            "beauty_clinic": [
                '["healthcare"="clinic"]["healthcare:speciality"~"dermatology|plastic_surgery"]',
                '["shop"="beauty"]',
            ],
            "nail": ['["shop"="beauty"]'],
            "spa": ['["leisure"="spa"]', '["shop"="massage"]'],
        },
        "auto": {
            "mechanic": ['["shop"="car_repair"]'],
            "tire": ['["shop"="tyres"]'],
            "carwash": ['["amenity"="car_wash"]'],
            "oil": ['["shop"="car_repair"]'],
            "parts": ['["shop"="car_parts"]'],
            "body": ['["shop"="car_repair"]'],
            "battery": ['["shop"="car_parts"]'],
            "motorcycle": ['["shop"="motorcycle"]'],
        },
        "home": {
            "electrician": ['["craft"="electrician"]'],
            "plumber": ['["craft"="plumber"]'],
            "ac": ['["craft"="hvac"]'],
            "appliance": ['["shop"="appliance"]'],
            "cleaning": ['["craft"="cleaning"]'],
            "carpentry": ['["craft"="carpenter"]'],
            "locksmith": ['["craft"="locksmith"]'],
            "moving": ['["office"="moving_company"]'],
        },
        "retail": {
            "clothing": ['["shop"="clothes"]'],
            "shoes": ['["shop"="shoes"]'],
            "mobile": ['["shop"="mobile_phone"]'],
            "computer": ['["shop"="computer"]'],
            "cosmetics": ['["shop"="cosmetics"]'],
            "home_goods": ['["shop"="houseware"]'],
            "jewelry": ['["shop"="jewelry"]'],
            "book": ['["shop"="books"]', '["shop"="stationery"]'],
        },
        "education": {
            "school": ['["amenity"="school"]', '["amenity"="training"]'],
            "language": ['["amenity"="language_school"]'],
            "tutoring": ['["amenity"="training"]'],
            "computer": ['["amenity"="training"]'],
            "art": ['["amenity"="music_school"]', '["amenity"="arts_centre"]'],
            "driving": ['["amenity"="driving_school"]'],
        },
        "fitness": {
            "gym": ['["leisure"="fitness_centre"]'],
            "pool": ['["leisure"="swimming_pool"]'],
            "sports_school": ['["leisure"="sports_centre"]'],
            "game": ['["leisure"="amusement_arcade"]'],
            "cinema": ['["amenity"="cinema"]'],
        },
        "professional": {
            "lawyer": ['["office"="lawyer"]'],
            "accounting": ['["office"="accountant"]'],
            "insurance": ['["office"="insurance"]'],
            "realestate": ['["office"="estate_agent"]'],
            "printing": ['["shop"="copyshop"]', '["craft"="printer"]'],
            "photography": ['["shop"="photo"]'],
            "it": ['["office"="it"]'],
        },
        "travel": {
            "hotel": ['["tourism"="hotel"]'],
            "guesthouse": ['["tourism"="guest_house"]'],
            "travel_agency": ['["shop"="travel_agency"]'],
            "rental": ['["amenity"="car_rental"]'],
        },
        "pet": {
            "vet": ['["amenity"="veterinary"]'],
            "petshop": ['["shop"="pet"]'],
        },
    }

    def connect() -> sqlite3.Connection:
        con = sqlite3.connect(str(db_path), timeout=20)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def init_db() -> None:
        with connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS businesses(
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    top TEXT NOT NULL,
                    sub TEXT NOT NULL,
                    city TEXT NOT NULL DEFAULT 'اهواز',
                    area TEXT NOT NULL DEFAULT '',
                    address TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    instagram TEXT NOT NULL DEFAULT '',
                    website TEXT NOT NULL DEFAULT '',
                    lat REAL,
                    lng REAL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    source_ref TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'approved',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_business_city ON businesses(city);
                CREATE INDEX IF NOT EXISTS idx_business_area ON businesses(area);
                CREATE INDEX IF NOT EXISTS idx_business_top_sub ON businesses(top, sub);

                CREATE TABLE IF NOT EXISTS osm_businesses(
                    source_ref TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    top TEXT NOT NULL,
                    sub TEXT NOT NULL,
                    city TEXT NOT NULL DEFAULT 'اهواز',
                    area TEXT NOT NULL DEFAULT '',
                    address TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    website TEXT NOT NULL DEFAULT '',
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    osm_tags TEXT NOT NULL DEFAULT '{}',
                    imported_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_osm_city ON osm_businesses(city);
                CREATE INDEX IF NOT EXISTS idx_osm_top_sub ON osm_businesses(top, sub);

                CREATE TABLE IF NOT EXISTS submissions(
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    top TEXT NOT NULL,
                    sub TEXT NOT NULL,
                    city TEXT NOT NULL DEFAULT 'اهواز',
                    area TEXT NOT NULL,
                    address TEXT NOT NULL,
                    phone TEXT NOT NULL DEFAULT '',
                    instagram TEXT NOT NULL DEFAULT '',
                    website TEXT NOT NULL DEFAULT '',
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    claimed_status TEXT NOT NULL DEFAULT 'unknown',
                    review_status TEXT NOT NULL DEFAULT 'pending',
                    submitted_at INTEGER NOT NULL,
                    reviewed_at INTEGER,
                    review_note TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_submission_review ON submissions(review_status, submitted_at);

                CREATE TABLE IF NOT EXISTS demands(
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    need_text TEXT NOT NULL DEFAULT '',
                    city TEXT NOT NULL DEFAULT 'اهواز',
                    area TEXT NOT NULL,
                    wait_hours INTEGER NOT NULL DEFAULT 72,
                    max_budget INTEGER NOT NULL DEFAULT 0,
                    preferences TEXT NOT NULL DEFAULT '',
                    contact TEXT NOT NULL DEFAULT '',
                    contact_type TEXT NOT NULL DEFAULT 'mobile',
                    source TEXT NOT NULL DEFAULT 'mvp',
                    status TEXT NOT NULL DEFAULT 'waiting',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_demands_created ON demands(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_demands_category_area ON demands(category, area);
                CREATE INDEX IF NOT EXISTS idx_demands_contact ON demands(contact);

                CREATE TABLE IF NOT EXISTS mvp_events(
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL DEFAULT '',
                    event_name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    area TEXT NOT NULL DEFAULT '',
                    meta_json TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_mvp_events_name_time ON mvp_events(event_name, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_mvp_events_session ON mvp_events(session_id);
                """
            )

    init_db()

    def clean(value: Any, max_len: int = 300) -> str:
        text = re.sub(r"[\x00-\x1f]+", " ", str(value or ""))
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_len]

    def norm(value: Any) -> str:
        return clean(value, 500).replace("ي", "ی").replace("ك", "ک").lower()

    def row_public(r: sqlite3.Row | dict[str, Any], source: str | None = None) -> dict[str, Any]:
        d = dict(r)
        return {
            "id": d.get("id") or "osm_" + re.sub(r"[^A-Za-z0-9]", "_", d.get("source_ref", "")),
            "name": d.get("name", ""),
            "top": d.get("top", "other"),
            "sub": d.get("sub", "other"),
            "city": d.get("city", "اهواز"),
            "area": d.get("area", ""),
            "address": d.get("address", ""),
            "phone": d.get("phone", ""),
            "instagram": d.get("instagram", ""),
            "website": d.get("website", ""),
            "lat": d.get("lat"),
            "lng": d.get("lng"),
            "source": source or d.get("source", "manual"),
            "sourceRef": d.get("source_ref", ""),
            "status": d.get("status", "approved"),
            "createdAt": d.get("created_at") or d.get("imported_at") or 0,
        }

    def authorized() -> bool:
        header = request.headers.get("Authorization", "")
        supplied = re.sub(r"^Bearer\s+", "", header, flags=re.I).strip()
        cookie = request.cookies.get(admin_cookie, "").strip()
        try:
            return bool(admin_token) and (
                (supplied and secrets.compare_digest(supplied, admin_token))
                or (cookie and secrets.compare_digest(cookie, admin_token))
            )
        except Exception:
            return False

    def valid_coords(lat: float, lng: float) -> bool:
        return 29 <= lat <= 33 and 46 <= lng <= 51

    def osm_filters(top: str, sub: str) -> list[str]:
        return osm_catalog.get(top, {}).get(sub, [])

    def osm_address(tags: dict[str, Any]) -> str:
        parts = [
            tags.get("addr:province"),
            tags.get("addr:city"),
            tags.get("addr:district"),
            tags.get("addr:suburb"),
            tags.get("addr:street"),
            tags.get("addr:housenumber"),
        ]
        out: list[str] = []
        for p in parts:
            p = clean(p, 100)
            if p and p not in out:
                out.append(p)
        return "، ".join(out)

    def osm_area(tags: dict[str, Any]) -> str:
        return clean(
            tags.get("addr:neighbourhood")
            or tags.get("addr:suburb")
            or tags.get("addr:district")
            or "",
            120,
        )

    def osm_item(el: dict[str, Any], top: str, sub: str) -> dict[str, Any] | None:
        tags = el.get("tags") or {}
        center = el.get("center") or {}
        lat = float(el.get("lat") if el.get("lat") is not None else center.get("lat", "nan"))
        lng = float(el.get("lon") if el.get("lon") is not None else center.get("lon", "nan"))
        name = clean(tags.get("name") or tags.get("name:fa") or tags.get("name:en"), 140)
        if not name or not valid_coords(lat, lng):
            return None
        return {
            "source_ref": f"{el.get('type')}/{el.get('id')}",
            "name": name,
            "top": top,
            "sub": sub,
            "city": "اهواز",
            "area": osm_area(tags),
            "address": osm_address(tags),
            "phone": clean(tags.get("phone") or tags.get("contact:phone"), 60),
            "website": clean(tags.get("website") or tags.get("contact:website"), 220),
            "lat": lat,
            "lng": lng,
            "tags": tags,
        }

    def overpass_fetch(top: str, sub: str) -> list[dict[str, Any]]:
        filters = osm_filters(top, sub)
        if not filters:
            raise ValueError("unsupported_category")
        union = []
        for flt in filters:
            union.extend(
                [
                    f"node{flt}({ahvaz_bbox});",
                    f"way{flt}({ahvaz_bbox});",
                    f"relation{flt}({ahvaz_bbox});",
                ]
            )
        query = "[out:json][timeout:25];(" + "".join(union) + ");out center tags;"
        last_error: Exception | None = None
        for endpoint in overpass_endpoints:
            try:
                r = requests.post(
                    endpoint,
                    data={"data": query},
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "AlanOffer-Ahvaz-Pilot/1.0",
                    },
                    timeout=35,
                )
                r.raise_for_status()
                body = r.json()
                result: list[dict[str, Any]] = []
                seen: set[str] = set()
                for el in body.get("elements") or []:
                    item = osm_item(el, top, sub)
                    if item and item["source_ref"] not in seen:
                        seen.add(item["source_ref"])
                        result.append(item)
                return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise RuntimeError(f"overpass_unreachable: {last_error}")

    @bp.after_request
    def add_cors(resp):
        origin = request.headers.get("Origin", "")
        if origin in cors_origins:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @bp.route("/api/<path:_path>", methods=["OPTIONS"])
    def options(_path: str):
        return ("", 204)

    @bp.get("/api/health")
    def health():
        with connect() as con:
            own = con.execute("SELECT COUNT(*) AS n FROM businesses WHERE status='approved'").fetchone()["n"]
            osm = con.execute("SELECT COUNT(*) AS n FROM osm_businesses").fetchone()["n"]
            pending = con.execute("SELECT COUNT(*) AS n FROM submissions WHERE review_status='pending'").fetchone()["n"]
            demands = con.execute("SELECT COUNT(*) AS n FROM demands").fetchone()["n"]
            active_contacts = con.execute("SELECT COUNT(*) AS n FROM demands WHERE contact<>''").fetchone()["n"]
        return jsonify(
            ok=True,
            service="alanoffer-python",
            city="اهواز",
            db=True,
            ownBusinesses=own,
            osmBusinesses=osm,
            pendingSubmissions=pending,
            demands=demands,
            activeDemandContacts=active_contacts,
            adminConfigured=True,
            time=time.time(),
        )

    @bp.get("/api/businesses")
    def businesses():
        q = norm(request.args.get("q", ""))
        city = clean(request.args.get("city", "اهواز"), 80)
        area = norm(request.args.get("area", ""))
        top = clean(request.args.get("top", ""), 80)
        sub = clean(request.args.get("sub", ""), 80)
        try:
            limit = min(max(int(request.args.get("limit", "100")), 1), 500)
        except Exception:
            limit = 100

        where = ["status='approved'", "city=?"]
        args: list[Any] = [city]
        if top:
            where.append("top=?")
            args.append(top)
        if sub:
            where.append("sub=?")
            args.append(sub)
        with connect() as con:
            own = [
                row_public(r)
                for r in con.execute(
                    "SELECT * FROM businesses WHERE " + " AND ".join(where) + " ORDER BY updated_at DESC LIMIT 1500",
                    args,
                ).fetchall()
            ]
            osm_where = ["city=?"]
            osm_args: list[Any] = [city]
            if top:
                osm_where.append("top=?")
                osm_args.append(top)
            if sub:
                osm_where.append("sub=?")
                osm_args.append(sub)
            osm_rows = [
                row_public(r, "osm")
                for r in con.execute(
                    "SELECT * FROM osm_businesses WHERE " + " AND ".join(osm_where) + " ORDER BY imported_at DESC LIMIT 1500",
                    osm_args,
                ).fetchall()
            ]

        own_keys = {norm(x["name"]) + "|" + norm(x["area"]) for x in own}
        merged = own + [x for x in osm_rows if norm(x["name"]) + "|" + norm(x["area"]) not in own_keys]
        out = []
        for r in merged:
            text = norm(" ".join([r["name"], r["area"], r["address"], r["top"], r["sub"]]))
            if q and q not in text:
                continue
            if area and area not in norm(r["area"]) and area not in norm(r["address"]):
                continue
            out.append(r)
            if len(out) >= limit:
                break
        return jsonify(
            items=out,
            count=len(out),
            attribution="© OpenStreetMap contributors · ODbL" if any(x["source"] == "osm" for x in out) else "",
        )

    @bp.post("/api/submissions")
    def submissions():
        b = request.get_json(silent=True) or {}
        name = clean(b.get("name"), 140)
        top = clean(b.get("top"), 60)
        sub = clean(b.get("sub"), 60)
        city = clean(b.get("city") or "اهواز", 80)
        area = clean(b.get("area"), 120)
        address = clean(b.get("address"), 350)
        phone = clean(b.get("phone"), 60)
        instagram = clean(b.get("instagram"), 100)
        website = clean(b.get("website"), 220)
        claimed = clean(b.get("status") or "unknown", 30)
        try:
            lat, lng = float(b.get("lat")), float(b.get("lng"))
        except Exception:
            return jsonify(error="invalid_coordinates"), 400
        if not all([name, top, sub, area, address]) or not valid_coords(lat, lng):
            return jsonify(error="invalid_business_submission"), 400
        sid = "s_" + str(int(time.time() * 1000)) + "_" + os.urandom(4).hex()
        now = int(time.time() * 1000)
        with connect() as con:
            dupe = con.execute(
                "SELECT id FROM businesses WHERE city=? AND lower(name)=lower(?) AND area=? LIMIT 1",
                (city, name, area),
            ).fetchone()
            if dupe:
                return jsonify(error="business_already_exists", id=dupe["id"]), 409
            con.execute(
                """
                INSERT INTO submissions(id,name,top,sub,city,area,address,phone,instagram,website,lat,lng,claimed_status,review_status,submitted_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?)
                """,
                (sid, name, top, sub, city, area, address, phone, instagram, website, lat, lng, claimed, now),
            )
        return jsonify(ok=True, id=sid, status="pending"), 202

    @bp.post("/api/demands")
    def create_demand():
        b = request.get_json(silent=True) or {}
        category = clean(b.get("category"), 60)
        need_text = clean(b.get("needText"), 220)
        city = clean(b.get("city") or "اهواز", 80)
        area = clean(b.get("area"), 120)
        preferences = clean(b.get("preferences"), 350)
        source = clean(b.get("source") or "mvp", 80)
        try:
            wait_hours = int(b.get("waitHours") or 72)
            max_budget = int(b.get("maxBudget") or 0)
        except Exception:
            return jsonify(error="invalid_demand_numbers"), 400
        wait_hours = max(1, min(wait_hours, 24 * 60))
        max_budget = max(0, min(max_budget, 2_000_000_000))
        allowed_categories = {"food", "dentist", "beauty", "auto", "home", "other"}
        if category not in allowed_categories or not area:
            return jsonify(error="invalid_demand"), 400
        if len(need_text) < 2:
            return jsonify(error="need_text_required"), 400
        did = "d_" + str(int(time.time() * 1000)) + "_" + os.urandom(4).hex()
        now = int(time.time() * 1000)
        with connect() as con:
            con.execute(
                """
                INSERT INTO demands(id,category,need_text,city,area,wait_hours,max_budget,preferences,source,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,'waiting',?,?)
                """,
                (did, category, need_text, city, area, wait_hours, max_budget, preferences, source, now, now),
            )
        return jsonify(ok=True, id=did, status="waiting", contactRequired=True), 201

    @bp.post("/api/demands/<did>/contact")
    def add_demand_contact(did: str):
        b = request.get_json(silent=True) or {}
        contact = clean(b.get("contact"), 80)
        contact_type = clean(b.get("contactType") or "mobile", 20)
        trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        digits = re.sub(r"\D+", "", contact.translate(trans))
        # Iranian mobile numbers: accept 09xxxxxxxxx or 989xxxxxxxxx for the MVP.
        if not (len(digits) == 11 and digits.startswith("09")) and not (len(digits) == 12 and digits.startswith("989")):
            return jsonify(error="invalid_mobile"), 400
        if len(digits) == 12 and digits.startswith("98"):
            digits = "0" + digits[2:]
        now = int(time.time() * 1000)
        with connect() as con:
            cur = con.execute(
                "UPDATE demands SET contact=?, contact_type=?, updated_at=? WHERE id=?",
                (digits, contact_type, now, clean(did, 80)),
            )
            if not cur.rowcount:
                return jsonify(error="demand_not_found"), 404
        return jsonify(ok=True, id=did, active=True)

    @bp.post("/api/mvp/events")
    def mvp_event():
        b = request.get_json(silent=True) or {}
        event_name = clean(b.get("event"), 60)
        session_id = clean(b.get("sessionId"), 100)
        category = clean(b.get("category"), 60)
        area = clean(b.get("area"), 120)
        if event_name not in {"page_view", "cta_click", "form_start", "demand_created", "contact_saved"}:
            return jsonify(error="invalid_event"), 400
        meta = b.get("meta") if isinstance(b.get("meta"), dict) else {}
        safe_meta = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))[:1200]
        eid = "e_" + str(int(time.time() * 1000)) + "_" + os.urandom(3).hex()
        with connect() as con:
            con.execute(
                "INSERT INTO mvp_events(id,session_id,event_name,category,area,meta_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (eid, session_id, event_name, category, area, safe_meta, int(time.time() * 1000)),
            )
        return jsonify(ok=True), 201

    @bp.get("/api/admin/demands")
    def admin_demands():
        if not authorized():
            return jsonify(error="admin_unauthorized", adminConfigured=True), 401
        try:
            limit = max(1, min(int(request.args.get("limit") or 100), 500))
        except Exception:
            limit = 100
        with connect() as con:
            rows = [dict(r) for r in con.execute(
                "SELECT * FROM demands ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()]
        return jsonify(items=rows, count=len(rows))

    @bp.get("/api/admin/mvp-stats")
    def admin_mvp_stats():
        if not authorized():
            return jsonify(error="admin_unauthorized", adminConfigured=True), 401
        with connect() as con:
            events = {r["event_name"]: r["n"] for r in con.execute(
                "SELECT event_name, COUNT(*) AS n FROM mvp_events GROUP BY event_name"
            ).fetchall()}
            unique_sessions = con.execute(
                "SELECT COUNT(DISTINCT session_id) AS n FROM mvp_events WHERE session_id<>''"
            ).fetchone()["n"]
            demand_count = con.execute("SELECT COUNT(*) AS n FROM demands").fetchone()["n"]
            contacts = con.execute("SELECT COUNT(*) AS n FROM demands WHERE contact<>''").fetchone()["n"]
        def rate(num: int, den: int) -> float:
            return round((num / den * 100), 1) if den else 0.0
        return jsonify(
            uniqueSessions=unique_sessions,
            events=events,
            demands=demand_count,
            contacts=contacts,
            pageToDemandRate=rate(demand_count, unique_sessions),
            demandToContactRate=rate(contacts, demand_count),
        )

    @bp.get("/api/osm/search")
    def osm_search():
        if not authorized():
            return jsonify(error="admin_unauthorized"), 401
        top = clean(request.args.get("top"), 60)
        sub = clean(request.args.get("sub"), 60)
        if not osm_filters(top, sub):
            return jsonify(error="unsupported_category"), 400
        try:
            items = overpass_fetch(top, sub)
        except Exception as exc:  # noqa: BLE001
            return jsonify(error="overpass_error", detail=str(exc)[:250]), 502
        preview = []
        for x in items[:250]:
            preview.append(
                {
                    "sourceRef": x["source_ref"],
                    "name": x["name"],
                    "top": x["top"],
                    "sub": x["sub"],
                    "city": x["city"],
                    "area": x["area"],
                    "address": x["address"],
                    "phone": x["phone"],
                    "website": x["website"],
                    "lat": x["lat"],
                    "lng": x["lng"],
                    "source": "osm",
                }
            )
        return jsonify(items=preview, count=len(preview), attribution="© OpenStreetMap contributors · ODbL")

    @bp.post("/api/osm/sync")
    def osm_sync():
        if not authorized():
            return jsonify(error="admin_unauthorized"), 401
        # Admin-only, fixed Ahvaz bbox + whitelisted OSM category.
        # Idempotent upsert; 5-minute cooldown per category prevents accidental hammering.
        b = request.get_json(silent=True) or {}
        top = clean(b.get("top") or request.args.get("top"), 60)
        sub = clean(b.get("sub") or request.args.get("sub"), 60)
        key = top + "/" + sub
        if not osm_filters(top, sub):
            return jsonify(error="unsupported_category"), 400
        with lock:
            elapsed = time.time() - last_sync.get(key, 0)
            if elapsed < 300:
                return jsonify(error="sync_cooldown", retryAfter=int(300 - elapsed)), 429
            last_sync[key] = time.time()
        try:
            items = overpass_fetch(top, sub)
        except Exception as exc:  # noqa: BLE001
            return jsonify(error="overpass_error", detail=str(exc)[:250]), 502
        now = int(time.time() * 1000)
        with connect() as con:
            for x in items:
                con.execute(
                    """
                    INSERT INTO osm_businesses(source_ref,name,top,sub,city,area,address,phone,website,lat,lng,osm_tags,imported_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(source_ref) DO UPDATE SET
                        name=excluded.name, top=excluded.top, sub=excluded.sub, city=excluded.city,
                        area=excluded.area, address=excluded.address, phone=excluded.phone,
                        website=excluded.website, lat=excluded.lat, lng=excluded.lng,
                        osm_tags=excluded.osm_tags, imported_at=excluded.imported_at
                    """,
                    (
                        x["source_ref"], x["name"], top, sub, "اهواز", x["area"], x["address"],
                        x["phone"], x["website"], x["lat"], x["lng"],
                        json.dumps(x["tags"], ensure_ascii=False), now,
                    ),
                )
        return jsonify(ok=True, imported=len(items), top=top, sub=sub, attribution="© OpenStreetMap contributors · ODbL")

    ADMIN_PAGE = r"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>مدیریت AlanOffer</title><style>
    :root{--o:#ff6a00;--ink:#171717;--mut:#777;--bg:#f5f6f7;--line:#e5e5e5}*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:Tahoma,Arial,sans-serif;color:var(--ink)}.w{max-width:920px;margin:auto;padding:14px}.hero,.card{background:#fff;border:1px solid var(--line);border-radius:20px;padding:16px;margin-bottom:12px}.hero{background:linear-gradient(135deg,#171717,#4a260c);color:#fff}.hero h1{margin:0 0 6px;font-size:24px}.mut{font-size:11px;line-height:1.9;color:var(--mut)}.hero .mut{color:#ddd}.grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}select,button{width:100%;min-height:45px;border-radius:12px;font:inherit}select{border:1px solid #ddd;background:#fff;padding:0 9px}button{border:0;background:var(--o);color:#fff;font-weight:900;cursor:pointer}.dark{background:#111}.soft{background:#eee;color:#222}.state{font-size:11px;margin-top:10px;line-height:1.8}.items{display:grid;gap:8px;margin-top:10px}.item{border:1px solid #e8e8e8;border-radius:14px;padding:11px}.item b{font-size:14px}.row{display:flex;justify-content:space-between;gap:8px;align-items:center}.actions{display:flex;gap:7px;margin-top:8px}.actions button{width:auto;min-height:36px;padding:0 12px;font-size:11px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}.stat{background:#f7f7f7;border-radius:13px;padding:10px;text-align:center}.stat b{display:block;font-size:20px}.logout{color:#fff;text-decoration:none;font-size:11px}@media(max-width:650px){.grid,.stats{grid-template-columns:1fr}.row{align-items:flex-start;flex-direction:column}}</style></head><body><div class="w"><div class="hero"><div class="row"><div><h1>الان‌آفر · مدیریت</h1><div class="mut">مدیریت داده‌های اهواز، OSM و ثبت‌های کاربران</div></div><a class="logout" href="/alanoffer/admin/logout">خروج</a></div><div class="stats"><div class="stat"><b id="own">—</b><span>اختصاصی</span></div><div class="stat"><b id="osm">—</b><span>OSM</span></div><div class="stat"><b id="pending">—</b><span>در انتظار</span></div></div></div>
<div class="card"><b>ورود داده از OpenStreetMap</b><div class="mut">نتایج فقط از محدوده اهواز گرفته می‌شوند. همگام‌سازی رکوردها را در لایه جداگانه OSM ذخیره می‌کند.</div><div class="grid" style="margin-top:10px"><select id="top"></select><select id="sub"></select><button onclick="preview()">پیش‌نمایش</button></div><div class="grid" style="margin-top:8px;grid-template-columns:1fr 1fr"><button class="dark" onclick="syncNow()">همگام‌سازی این دسته</button><button class="soft" onclick="refreshAll()">تازه‌سازی وضعیت</button></div><div id="osmState" class="state"></div><div id="osmItems" class="items"></div><div class="mut">© OpenStreetMap contributors · ODbL</div></div>
<div class="card"><div class="row"><b>درخواست‌های MVP کاربران</b><button class="soft" style="width:auto;padding:0 12px" onclick="loadDemands()">تازه‌سازی</button></div><div id="mvpStats" class="state"></div><div id="demandItems" class="items"></div></div>
<div class="card"><div class="row"><b>ثبت‌های در انتظار تأیید</b><button class="soft" style="width:auto;padding:0 12px" onclick="loadPending()">تازه‌سازی</button></div><div id="pendingState" class="state"></div><div id="pendingItems" class="items"></div></div></div><script>
const C={food:{restaurant:'رستوران',fastfood:'فست‌فود',cafe:'کافه',juice:'آبمیوه/بستنی'},grocery:{supermarket:'سوپرمارکت',bakery:'نانوایی',pastry:'قنادی',produce:'میوه و سبزی'},health:{dentist:'دندانپزشک',dental_specialist:'متخصص دندانپزشکی',general_doctor:'پزشک عمومی',specialist_doctor:'پزشک متخصص',clinic:'کلینیک',hospital:'بیمارستان',pharmacy:'داروخانه',lab:'آزمایشگاه',imaging:'تصویربرداری',physio:'فیزیوتراپی',psychology:'روانشناسی',optometry:'عینک/اپتومتری',hearing:'شنوایی'},beauty:{barber:'آرایشگاه',salon:'سالن',beauty_clinic:'کلینیک زیبایی'},auto:{mechanic:'تعمیرگاه',tire:'لاستیک',carwash:'کارواش',parts:'لوازم یدکی'},home:{electrician:'برقکار',plumber:'لوله‌کش',ac:'تهویه'},retail:{clothing:'پوشاک',shoes:'کفش',mobile:'موبایل',computer:'کامپیوتر',cosmetics:'آرایشی',jewelry:'طلا و جواهر'},education:{school:'آموزشگاه',language:'زبان',driving:'رانندگی'},fitness:{gym:'باشگاه',pool:'استخر',cinema:'سینما'},professional:{lawyer:'وکیل',accounting:'حسابداری',insurance:'بیمه',realestate:'املاک',printing:'چاپ',photography:'عکاسی',it:'IT'},travel:{hotel:'هتل',guesthouse:'مهمانپذیر',travel_agency:'آژانس',rental:'اجاره خودرو'},pet:{vet:'دامپزشکی',petshop:'پت‌شاپ'}};
const TL={food:'غذا',grocery:'خواربار',health:'سلامت',beauty:'زیبایی',auto:'خودرو',home:'خدمات منزل',retail:'فروشگاه',education:'آموزش',fitness:'ورزش/تفریح',professional:'خدمات حرفه‌ای',travel:'سفر',pet:'حیوانات'};const E=id=>document.getElementById(id);function esc(s){return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}async function A(u,o={}){let r=await fetch(u,{credentials:'same-origin',...o,headers:{'Content-Type':'application/json',...(o.headers||{})}}),d={};try{d=await r.json()}catch{}if(!r.ok)throw Error(d.error||('HTTP '+r.status));return d}
function tops(){E('top').innerHTML=Object.keys(C).map(k=>`<option value="${k}">${TL[k]||k}</option>`).join('');E('top').value='health';subs()}function subs(){let k=E('top').value;E('sub').innerHTML=Object.entries(C[k]||{}).map(([x,l])=>`<option value="${x}">${l}</option>`).join('');if(k==='health')E('sub').value='dentist'}E('top').addEventListener('change',subs);
async function health(){let d=await A('/alanoffer/api/health');E('own').textContent=d.ownBusinesses;E('osm').textContent=d.osmBusinesses;E('pending').textContent=d.pendingSubmissions}
async function preview(){E('osmState').textContent='در حال دریافت از OSM…';E('osmItems').innerHTML='';try{let d=await A(`/alanoffer/api/osm/search?top=${encodeURIComponent(E('top').value)}&sub=${encodeURIComponent(E('sub').value)}`);E('osmState').textContent=`${d.count} نتیجه پیدا شد.`;E('osmItems').innerHTML=(d.items||[]).slice(0,40).map(x=>`<div class="item"><b>${esc(x.name)}</b><div class="mut">${esc(x.area||x.address||'آدرس در OSM کامل نیست')}</div></div>`).join('')||'<div class="mut">نتیجه‌ای نبود.</div>'}catch(e){E('osmState').textContent='خطا: '+e.message}}
async function syncNow(){if(!confirm('این دسته از OSM در بانک AlanOffer همگام شود؟'))return;E('osmState').textContent='در حال همگام‌سازی…';try{let d=await A('/alanoffer/api/osm/sync',{method:'POST',body:JSON.stringify({top:E('top').value,sub:E('sub').value})});E('osmState').textContent=`✓ ${d.imported} رکورد همگام شد.`;await health()}catch(e){E('osmState').textContent='خطا: '+e.message}}
async function loadDemands(){E('mvpStats').textContent='در حال دریافت…';try{let [s,d]=await Promise.all([A('/alanoffer/api/admin/mvp-stats'),A('/alanoffer/api/admin/demands?limit=100')]);E('mvpStats').textContent=`بازدید یکتا: ${s.uniqueSessions} · درخواست: ${s.demands} · شماره فعال: ${s.contacts} · تبدیل بازدید→درخواست: ${s.pageToDemandRate}٪ · درخواست→شماره: ${s.demandToContactRate}٪`;const L={food:'غذا',dentist:'دندانپزشکی',beauty:'زیبایی',auto:'خودرو',home:'خدمات منزل',other:'سایر'};E('demandItems').innerHTML=(d.items||[]).map(x=>`<div class="item"><b>${esc(L[x.category]||x.category)} · ${esc(x.area)}</b><div class="mut">${esc(x.need_text||'')} ${x.max_budget?`· بودجه تا ${Number(x.max_budget).toLocaleString('fa-IR')} تومان`:''}<br>انتظار: ${x.wait_hours} ساعت · ${x.contact?`☎ ${esc(x.contact)}`:'بدون شماره'}${x.preferences?`<br>${esc(x.preferences)}`:''}</div></div>`).join('')||'<div class="mut">هنوز درخواستی ثبت نشده.</div>'}catch(e){E('mvpStats').textContent='خطا: '+e.message}}
async function loadPending(){E('pendingState').textContent='در حال دریافت…';try{let d=await A('/alanoffer/api/admin/submissions?status=pending');E('pendingState').textContent=`${d.count} ثبت در انتظار است.`;E('pendingItems').innerHTML=(d.items||[]).map(x=>`<div class="item"><b>${esc(x.name)}</b><div class="mut">${esc(x.area)} · ${esc(x.address)}<br>${esc(x.phone||'')}</div><div class="actions"><button onclick="review('${x.id}','approve')">تأیید</button><button class="dark" onclick="review('${x.id}','reject')">رد</button></div></div>`).join('')||'<div class="mut">درخواستی در انتظار نیست.</div>'}catch(e){E('pendingState').textContent='خطا: '+e.message}}
async function review(id,a){try{await A(`/alanoffer/api/admin/submissions/${encodeURIComponent(id)}/${a}`,{method:'POST',body:a==='reject'?JSON.stringify({note:'رد توسط مدیر'}):'{}'});await refreshAll()}catch(e){alert(e.message)}}async function refreshAll(){await health();await Promise.all([loadPending(),loadDemands()])}tops();refreshAll();</script></body></html>"""

    @bp.get("/admin/setup/<secret>")
    def admin_setup(secret: str):
        if not setup_secret:
            return ("راه‌اندازی دستگاه جدید غیرفعال است.", 503)
        if not secrets.compare_digest(secret, setup_secret):
            return ("لینک راه‌اندازی نامعتبر است.", 403)
        # Strong private pairing link: usable on the owner's trusted devices.
        setup_used_file.write_text(str(int(time.time())), encoding="utf-8")
        resp = make_response(redirect("/alanoffer/admin"))
        resp.set_cookie(admin_cookie, admin_token, max_age=60*60*24*180, secure=True, httponly=True, samesite="Lax", path="/alanoffer")
        return resp

    @bp.get("/admin")
    def admin_page():
        if not authorized():
            return ("دسترسی مدیریت روی این دستگاه فعال نشده است.", 401)
        return render_template_string(ADMIN_PAGE)

    @bp.get("/admin/logout")
    def admin_logout():
        resp = make_response("از مدیریت خارج شدی. برای ورود مجدد باید کوکی مدیریت دوباره تنظیم شود.")
        resp.delete_cookie(admin_cookie, path="/alanoffer")
        return resp

    @bp.post("/api/admin/businesses")
    def admin_add_business():
        if not authorized():
            return jsonify(error="admin_unauthorized", adminConfigured=True), 401
        b = request.get_json(silent=True) or {}
        name = clean(b.get("name"), 140)
        top = clean(b.get("top"), 60)
        sub = clean(b.get("sub"), 60)
        city = clean(b.get("city") or "اهواز", 80)
        area = clean(b.get("area"), 120)
        address = clean(b.get("address"), 350)
        phone = clean(b.get("phone"), 60)
        instagram = clean(b.get("instagram"), 100)
        website = clean(b.get("website"), 220)
        source = clean(b.get("source") or "admin", 50)
        source_ref = clean(b.get("sourceRef") or "", 180)
        try:
            lat = float(b.get("lat")) if b.get("lat") not in (None, "") else None
            lng = float(b.get("lng")) if b.get("lng") not in (None, "") else None
        except Exception:
            return jsonify(error="invalid_coordinates"), 400
        if not all([name, top, sub, area, address]):
            return jsonify(error="invalid_business"), 400
        if lat is not None and lng is not None and not valid_coords(lat, lng):
            return jsonify(error="invalid_coordinates"), 400
        now = int(time.time() * 1000)
        bid = "b_" + str(now) + "_" + os.urandom(4).hex()
        with connect() as con:
            con.execute(
                """
                INSERT INTO businesses(id,name,top,sub,city,area,address,phone,instagram,website,lat,lng,source,source_ref,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'approved',?,?)
                """,
                (bid, name, top, sub, city, area, address, phone, instagram, website, lat, lng, source, source_ref, now, now),
            )
        return jsonify(ok=True, id=bid), 201

    @bp.get("/api/admin/submissions")
    def admin_submissions():
        if not authorized():
            return jsonify(error="admin_unauthorized", adminConfigured=True), 401
        status = clean(request.args.get("status") or "pending", 30)
        with connect() as con:
            rows = [dict(r) for r in con.execute(
                "SELECT * FROM submissions WHERE review_status=? ORDER BY submitted_at ASC LIMIT 500", (status,)
            ).fetchall()]
        return jsonify(items=rows, count=len(rows))

    @bp.post("/api/admin/submissions/<sid>/approve")
    def admin_approve(sid: str):
        if not authorized():
            return jsonify(error="admin_unauthorized", adminConfigured=True), 401
        now = int(time.time() * 1000)
        with connect() as con:
            s = con.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
            if not s:
                return jsonify(error="submission_not_found"), 404
            if s["review_status"] != "pending":
                return jsonify(error="submission_already_reviewed"), 409
            bid = "b_" + str(now) + "_" + os.urandom(4).hex()
            con.execute(
                """
                INSERT INTO businesses(id,name,top,sub,city,area,address,phone,instagram,website,lat,lng,source,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'approved',?,?)
                """,
                (bid, s["name"], s["top"], s["sub"], s["city"], s["area"], s["address"], s["phone"], s["instagram"], s["website"], s["lat"], s["lng"], "user", now, now),
            )
            con.execute("UPDATE submissions SET review_status='approved', reviewed_at=? WHERE id=?", (now, sid))
        return jsonify(ok=True, businessId=bid)

    @bp.post("/api/admin/submissions/<sid>/reject")
    def admin_reject(sid: str):
        if not authorized():
            return jsonify(error="admin_unauthorized", adminConfigured=True), 401
        note = clean((request.get_json(silent=True) or {}).get("note"), 250)
        now = int(time.time() * 1000)
        with connect() as con:
            cur = con.execute(
                "UPDATE submissions SET review_status='rejected', reviewed_at=?, review_note=? WHERE id=? AND review_status='pending'",
                (now, note, sid),
            )
            if not cur.rowcount:
                return jsonify(error="pending_submission_not_found"), 404
        return jsonify(ok=True)

    return bp
