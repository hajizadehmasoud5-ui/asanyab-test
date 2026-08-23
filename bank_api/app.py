import os
from contextlib import contextmanager
from html import escape
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI(title="DrLinq Provider Bank", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://drlinq.ir", "https://www.drlinq.ir"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def dsn() -> str:
    host = os.environ.get("DB_HOST", "postgres")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ["DB_NAME"]
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    return f"host={host} port={port} dbname={name} user={user} password={password}"


@contextmanager
def db():
    with psycopg.connect(dsn(), row_factory=dict_row) as conn:
        yield conn


@app.on_event("startup")
def startup() -> None:
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with db() as conn:
        conn.execute(schema)
        conn.commit()


@app.get("/health")
def health():
    with db() as conn:
        value = conn.execute("SELECT 1 AS ok").fetchone()
    return {"ok": bool(value and value["ok"] == 1), "service": "drlinq-bank-api"}


@app.get("/stats")
def stats():
    with db() as conn:
        counts = conn.execute(
            """
            SELECT
              (SELECT count(*) FROM bank_providers WHERE active) AS providers,
              (SELECT count(*) FROM bank_locations) AS locations,
              (SELECT count(*) FROM bank_contracts WHERE status='active') AS contracts,
              (SELECT count(*) FROM bank_insurers WHERE active) AS insurers,
              (SELECT count(*) FROM bank_sources WHERE active) AS sources
            """
        ).fetchone()
        latest = conn.execute(
            "SELECT finished_at, status, fetched_count, accepted_count, rejected_count FROM bank_ingestion_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    return {"counts": counts, "latest_ingestion": latest}


@app.get("/filters")
def filters():
    with db() as conn:
        insurers = conn.execute("SELECT name FROM bank_insurers WHERE active ORDER BY name").fetchall()
        provinces = conn.execute("SELECT DISTINCT province FROM bank_locations WHERE province IS NOT NULL AND province<>'' ORDER BY province").fetchall()
        cities = conn.execute("SELECT DISTINCT city FROM bank_locations WHERE city IS NOT NULL AND city<>'' ORDER BY city LIMIT 500").fetchall()
        services = conn.execute("SELECT name FROM bank_services ORDER BY name LIMIT 500").fetchall()
    return {
        "insurers": [x["name"] for x in insurers],
        "provinces": [x["province"] for x in provinces],
        "cities": [x["city"] for x in cities],
        "services": [x["name"] for x in services],
    }


@app.get("/providers")
def providers(
    q: str = "",
    insurer: str = "",
    service: str = "",
    province: str = "",
    city: str = "",
    district: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    clauses = ["p.active = TRUE", "c.status = 'active'"]
    params: list[object] = []
    if q:
        clauses.append("(p.name ILIKE %s OR l.address ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    if insurer:
        clauses.append("i.name = %s")
        params.append(insurer)
    if service:
        clauses.append("s.name = %s")
        params.append(service)
    if province:
        clauses.append("l.province = %s")
        params.append(province)
    if city:
        clauses.append("l.city = %s")
        params.append(city)
    if district:
        clauses.append("l.district = %s")
        params.append(district)

    sql = f"""
      SELECT DISTINCT
        p.id, p.name, p.provider_type, p.phone, p.website,
        l.province, l.city, l.district, l.address, l.latitude, l.longitude,
        i.name AS insurer,
        c.confidence, c.last_verified_at,
        src.url AS source_url
      FROM bank_providers p
      JOIN bank_provider_locations pl ON pl.provider_id=p.id
      JOIN bank_locations l ON l.id=pl.location_id
      JOIN bank_contracts c ON c.provider_id=p.id AND c.location_id=l.id
      JOIN bank_insurers i ON i.id=c.insurer_id
      JOIN bank_sources src ON src.id=c.source_id
      LEFT JOIN bank_provider_services ps ON ps.provider_id=p.id
      LEFT JOIN bank_services s ON s.id=ps.service_id
      WHERE {' AND '.join(clauses)}
      ORDER BY p.name, l.city
      LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"items": rows, "limit": limit, "offset": offset}


@app.get("/view", response_class=HTMLResponse)
def view():
    summary = stats()["counts"]
    items = providers(
        insurer="بیمه دی",
        service="دندانپزشکی",
        province="خوزستان",
        city="اهواز",
        limit=100,
        offset=0,
    )["items"]
    cards = []
    for item in items:
        phone = escape(item.get("phone") or "—")
        address = escape(item.get("address") or "—")
        name = escape(item.get("name") or "—")
        insurer = escape(item.get("insurer") or "—")
        source = escape(item.get("source_url") or "#", quote=True)
        label = "منبع رسمی" if item.get("confidence") == "official" else "منبع ثانویه؛ قبل از مراجعه استعلام شود"
        cls = "official" if item.get("confidence") == "official" else "secondary"
        cards.append(
            f"<article class='card'><h2>{name}</h2>"
            f"<p><b>بیمه:</b> {insurer}</p><p><b>تلفن:</b> {phone}</p>"
            f"<p><b>آدرس:</b> {address}</p>"
            f"<div class='source {cls}'>{label} · <a href='{source}' target='_blank' rel='noopener'>مشاهده منبع</a></div></article>"
        )
    html = f"""<!doctype html>
<html lang='fa' dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>بانک مراکز دکترلینک</title><style>
body{{margin:0;background:#f5f7fb;color:#172033;font-family:Tahoma,Arial,sans-serif}}.wrap{{max-width:980px;margin:auto;padding:24px 14px 60px}}
h1{{color:#12213a;margin-bottom:6px}}.sub{{color:#667085;font-size:13px;line-height:1.9}}.stats{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:18px 0}}
.stat,.card{{background:white;border:1px solid #e5e7eb;border-radius:14px;padding:14px}}.stat b{{font-size:23px;color:#12213a;display:block}}.stat span{{font-size:11px;color:#667085}}
.grid{{display:grid;gap:10px}}h2{{font-size:17px;margin:0 0 10px;color:#12213a}}p{{margin:5px 0;font-size:13px;line-height:1.9}}.source{{border-top:1px dashed #e5e7eb;margin-top:10px;padding-top:9px;font-size:12px}}
.secondary{{color:#9a6700}}.official{{color:#087443}}a{{color:#2563eb;text-decoration:none}}.notice{{background:#fff8e6;border:1px solid #f5d58a;border-radius:12px;padding:11px;font-size:12px;line-height:1.8;margin-bottom:14px}}
@media(max-width:700px){{.stats{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main class='wrap'><h1>بانک مراکز دکترلینک</h1><div class='sub'>نمای زنده پایلوت: دندانپزشکی اهواز + بیمه دی</div>
<div class='stats'><div class='stat'><b>{summary['providers']}</b><span>مرکز</span></div><div class='stat'><b>{summary['locations']}</b><span>آدرس</span></div><div class='stat'><b>{summary['contracts']}</b><span>رابطه بیمه‌ای</span></div><div class='stat'><b>{summary['insurers']}</b><span>بیمه</span></div><div class='stat'><b>{summary['sources']}</b><span>منبع</span></div></div>
<div class='notice'>این نسخه آزمایشی است. رکوردهای فعلی از منبع ثانویه وارد شده‌اند و قبل از مراجعه باید قرارداد فعال با بیمه از مرکز یا بیمه استعلام شود.</div>
<div class='grid'>{''.join(cards)}</div></main></body></html>"""
    return HTMLResponse(html)
