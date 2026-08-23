import os
from contextlib import contextmanager
from html import escape
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI(title="DrLinq Provider Bank", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://drlinq.ir", "https://www.drlinq.ir"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def dsn() -> str:
    return " ".join([
        f"host={os.environ.get('DB_HOST', 'postgres')}",
        f"port={os.environ.get('DB_PORT', '5432')}",
        f"dbname={os.environ['DB_NAME']}",
        f"user={os.environ['DB_USER']}",
        f"password={os.environ['DB_PASSWORD']}",
    ])


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
              (SELECT count(DISTINCT insurer_id) FROM bank_contracts WHERE status='active') AS insurers_with_data,
              (SELECT count(*) FROM bank_sources WHERE active) AS sources,
              (SELECT count(*) FROM bank_services) AS services
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
        cities = conn.execute("SELECT DISTINCT city FROM bank_locations WHERE city IS NOT NULL AND city<>'' ORDER BY city LIMIT 1000").fetchall()
        services = conn.execute("SELECT DISTINCT name FROM bank_services ORDER BY name LIMIT 1000").fetchall()
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
        clauses.append("(p.name ILIKE %s OR l.address ILIKE %s OR p.phone ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
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
        clauses.append("l.district ILIKE %s")
        params.append(f"%{district}%")

    sql = f"""
      SELECT DISTINCT
        p.id, p.name, p.provider_type, p.phone, p.website,
        l.province, l.city, l.district, l.address, l.latitude, l.longitude,
        i.name AS insurer,
        c.confidence, c.last_verified_at,
        src.name AS source_name, src.url AS source_url, src.source_type
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


def option_html(values, selected_value, placeholder):
    parts = [f"<option value=''>{escape(placeholder)}</option>"]
    for value in values:
        safe = escape(str(value), quote=True)
        selected = " selected" if str(value) == selected_value else ""
        parts.append(f"<option value='{safe}'{selected}>{safe}</option>")
    return "".join(parts)


@app.get("/view", response_class=HTMLResponse)
def view(
    q: str = "",
    insurer: str = "",
    service: str = "",
    province: str = "",
    city: str = "",
    district: str = "",
):
    summary = stats()["counts"]
    fs = filters()
    items = providers(q=q, insurer=insurer, service=service, province=province, city=city, district=district, limit=100, offset=0)["items"]

    cards = []
    for item in items:
        phone = escape(item.get("phone") or "—")
        address = escape(item.get("address") or "—")
        name = escape(item.get("name") or "—")
        insurer_name = escape(item.get("insurer") or "—")
        province_name = escape(item.get("province") or "—")
        city_name = escape(item.get("city") or "—")
        district_name = escape(item.get("district") or "—")
        source_name = escape(item.get("source_name") or "منبع ثبت‌شده")
        source_url = escape(item.get("source_url") or "#", quote=True)
        official = item.get("confidence") == "official" or item.get("source_type") == "official"
        label = "منبع رسمی" if official else "منبع ثانویه؛ قبل از مراجعه استعلام شود"
        cls = "official" if official else "secondary"
        verified = escape(str(item.get("last_verified_at") or "—"))
        cards.append(
            f"<article class='card'><h2>{name}</h2>"
            f"<div class='facts'><span><b>بیمه:</b> {insurer_name}</span><span><b>استان:</b> {province_name}</span><span><b>شهر:</b> {city_name}</span><span><b>منطقه:</b> {district_name}</span></div>"
            f"<p><b>تلفن:</b> {phone}</p><p><b>آدرس:</b> {address}</p>"
            f"<div class='source {cls}'><span>{label}</span><span>{source_name}</span><span>آخرین ثبت/بررسی: {verified}</span> · <a href='{source_url}' target='_blank' rel='noopener'>مشاهده منبع</a></div></article>"
        )

    html = f"""<!doctype html>
<html lang='fa' dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>بانک سراسری مراکز دکترلینک</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f7fb;color:#172033;font-family:Tahoma,Arial,sans-serif}}.wrap{{max-width:1120px;margin:auto;padding:22px 14px 60px}}
.top{{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}}h1{{color:#12213a;margin:0 0 6px;font-size:26px}}.sub{{color:#667085;font-size:12px;line-height:1.9}}.home{{background:#12213a;color:#fff;text-decoration:none;padding:10px 13px;border-radius:10px;font-size:11px}}
.stats{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:18px 0}}.stat,.card,.search{{background:white;border:1px solid #e5e7eb;border-radius:14px;padding:14px}}.stat b{{font-size:22px;color:#12213a;display:block}}.stat span{{font-size:10px;color:#667085}}
.search{{margin-bottom:15px}}.fields{{display:grid;grid-template-columns:1.5fr repeat(5,1fr);gap:8px}}input,select,button{{width:100%;min-height:43px;border:1px solid #d6dbe4;border-radius:10px;background:#fff;padding:8px 10px;font:inherit;font-size:11px}}button{{background:#1769e0;color:white;border:0;font-weight:800;cursor:pointer;margin-top:8px}}
.meta{{display:flex;justify-content:space-between;gap:10px;color:#667085;font-size:11px;margin:8px 2px 12px}}.grid{{display:grid;gap:10px}}h2{{font-size:16px;margin:0 0 9px;color:#12213a}}p{{margin:5px 0;font-size:12px;line-height:1.9}}.facts{{display:flex;gap:6px 14px;flex-wrap:wrap;font-size:11px;color:#475467}}
.source{{border-top:1px dashed #e5e7eb;margin-top:10px;padding-top:9px;font-size:10px;display:flex;gap:7px;flex-wrap:wrap;align-items:center}}.secondary{{color:#9a6700}}.official{{color:#087443}}a{{color:#2563eb;text-decoration:none}}.notice{{background:#fff8e6;border:1px solid #f5d58a;border-radius:12px;padding:10px;font-size:11px;line-height:1.8;margin-bottom:14px}}.empty{{background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:28px;text-align:center;color:#667085;font-size:12px}}
@media(max-width:900px){{.stats{{grid-template-columns:repeat(3,1fr)}}.fields{{grid-template-columns:1fr 1fr}}}}@media(max-width:520px){{.stats{{grid-template-columns:repeat(2,1fr)}}.fields{{grid-template-columns:1fr}}.top{{display:block}}.home{{display:inline-block;margin-top:8px}}}}
</style></head><body><main class='wrap'>
<div class='top'><div><h1>بانک سراسری مراکز دکترلینک</h1><div class='sub'>جست‌وجو بر اساس بیمه، خدمت/تخصص، استان، شهر و منطقه. بانک به‌صورت زنده و منبع‌محور در حال تکمیل است.</div></div><a class='home' href='https://drlinq.ir/'>بازگشت به دکترلینک</a></div>
<div class='stats'><div class='stat'><b>{summary.get('providers',0)}</b><span>مرکز</span></div><div class='stat'><b>{summary.get('locations',0)}</b><span>آدرس</span></div><div class='stat'><b>{summary.get('contracts',0)}</b><span>رابطه بیمه‌ای</span></div><div class='stat'><b>{summary.get('insurers_with_data',0)} / {summary.get('insurers',0)}</b><span>بیمه دارای داده / فهرست</span></div><div class='stat'><b>{summary.get('services',0)}</b><span>خدمت/تخصص</span></div><div class='stat'><b>{summary.get('sources',0)}</b><span>منبع فعال</span></div></div>
<form class='search' method='get'><div class='fields'>
<input name='q' value='{escape(q,quote=True)}' placeholder='نام مرکز، آدرس یا تلفن'>
<select name='insurer'>{option_html(fs['insurers'], insurer, 'همه بیمه‌ها')}</select>
<select name='service'>{option_html(fs['services'], service, 'همه خدمات/تخصص‌ها')}</select>
<select name='province'>{option_html(fs['provinces'], province, 'همه استان‌ها')}</select>
<select name='city'>{option_html(fs['cities'], city, 'همه شهرها')}</select>
<input name='district' value='{escape(district,quote=True)}' placeholder='منطقه'>
</div><button type='submit'>جست‌وجو در بانک</button></form>
<div class='notice'>اصل اعتبار: وجود نام یک مرکز در منبع ثانویه به معنی تضمین قرارداد فعال امروز یا پوشش همه خدمات آن مرکز نیست. رکوردهای رسمی و ثانویه جداگانه علامت‌گذاری می‌شوند.</div>
<div class='meta'><span>{len(items)} نتیجه در این صفحه</span><span>حداکثر ۱۰۰ نتیجه نمایش داده می‌شود</span></div>
<div class='grid'>{''.join(cards) if cards else "<div class='empty'>برای این ترکیب هنوز نتیجه ثبت نشده است.</div>"}</div>
</main></body></html>"""
    return HTMLResponse(html)
