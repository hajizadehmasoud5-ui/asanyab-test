import json
import os
import re
from contextlib import contextmanager
from html import escape
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI(title="DrLinq Provider Bank", version="0.3.0")
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


def norm(value: str) -> str:
    value = (value or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    return re.sub(r"\s+", " ", value).strip().lower()


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


def service_match_sql(alias: str = "s") -> str:
    return f"""(
        {alias}.normalized_name = %s
        OR {alias}.normalized_name IN (
            SELECT a.normalized_alias
            FROM bank_service_aliases a
            JOIN bank_services canonical ON canonical.id=a.service_id
            WHERE canonical.normalized_name=%s
        )
    )"""


def available_options(insurer: str = "", service: str = "", province: str = ""):
    with db() as conn:
        insurers = conn.execute(
            """SELECT DISTINCT i.name
               FROM bank_contracts c
               JOIN bank_insurers i ON i.id=c.insurer_id
               WHERE c.status='active'
               ORDER BY i.name"""
        ).fetchall()

        service_clauses = ["c.status='active'", "p.active=TRUE"]
        service_params = []
        if insurer:
            service_clauses.append("i.name=%s")
            service_params.append(insurer)
        services = conn.execute(
            f"""SELECT DISTINCT s.name
                FROM bank_contracts c
                JOIN bank_insurers i ON i.id=c.insurer_id
                JOIN bank_providers p ON p.id=c.provider_id
                JOIN bank_provider_services ps ON ps.provider_id=p.id
                JOIN bank_services s ON s.id=ps.service_id
                WHERE {' AND '.join(service_clauses)}
                ORDER BY s.name""",
            service_params,
        ).fetchall()

        province_clauses = ["c.status='active'", "p.active=TRUE", "l.province IS NOT NULL", "l.province<>''"]
        province_params = []
        if insurer:
            province_clauses.append("i.name=%s")
            province_params.append(insurer)
        if service:
            province_clauses.append(service_match_sql("s"))
            nservice = norm(service)
            province_params.extend([nservice, nservice])
        provinces = conn.execute(
            f"""SELECT DISTINCT l.province
                FROM bank_contracts c
                JOIN bank_insurers i ON i.id=c.insurer_id
                JOIN bank_providers p ON p.id=c.provider_id
                JOIN bank_provider_locations pl ON pl.provider_id=p.id AND pl.location_id=c.location_id
                JOIN bank_locations l ON l.id=pl.location_id
                LEFT JOIN bank_provider_services ps ON ps.provider_id=p.id
                LEFT JOIN bank_services s ON s.id=ps.service_id
                WHERE {' AND '.join(province_clauses)}
                ORDER BY l.province""",
            province_params,
        ).fetchall()

        city_clauses = ["c.status='active'", "p.active=TRUE", "l.city IS NOT NULL", "l.city<>''"]
        city_params = []
        if insurer:
            city_clauses.append("i.name=%s")
            city_params.append(insurer)
        if service:
            city_clauses.append(service_match_sql("s"))
            nservice = norm(service)
            city_params.extend([nservice, nservice])
        if province:
            city_clauses.append("l.province=%s")
            city_params.append(province)
        cities = conn.execute(
            f"""SELECT DISTINCT l.city
                FROM bank_contracts c
                JOIN bank_insurers i ON i.id=c.insurer_id
                JOIN bank_providers p ON p.id=c.provider_id
                JOIN bank_provider_locations pl ON pl.provider_id=p.id AND pl.location_id=c.location_id
                JOIN bank_locations l ON l.id=pl.location_id
                LEFT JOIN bank_provider_services ps ON ps.provider_id=p.id
                LEFT JOIN bank_services s ON s.id=ps.service_id
                WHERE {' AND '.join(city_clauses)}
                ORDER BY l.city""",
            city_params,
        ).fetchall()

    return {
        "insurers": [x["name"] for x in insurers],
        "services": [x["name"] for x in services],
        "provinces": [x["province"] for x in provinces],
        "cities": [x["city"] for x in cities],
    }


@app.get("/filters")
def filters(insurer: str = "", service: str = "", province: str = ""):
    return available_options(insurer=insurer, service=service, province=province)


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
        clauses.append(service_match_sql("s"))
        nservice = norm(service)
        params.extend([nservice, nservice])
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


def insurer_has_data(name: str) -> bool:
    if not name:
        return True
    with db() as conn:
        row = conn.execute(
            """SELECT 1 FROM bank_contracts c
               JOIN bank_insurers i ON i.id=c.insurer_id
               WHERE c.status='active' AND i.name=%s LIMIT 1""",
            (name,),
        ).fetchone()
    return bool(row)


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
    fs = available_options(insurer=insurer, service=service, province=province)
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

    if not items and insurer and not insurer_has_data(insurer):
        empty_message = "این بیمه هنوز دادهٔ مرکز درمانی واردشده ندارد؛ به محض اتصال منبع، در جست‌وجو فعال می‌شود."
    elif not items:
        empty_message = "برای این ترکیبِ بیمه، خدمت و موقعیت هنوز نتیجه ثبت نشده است. یکی از فیلترها را تغییر بده."
    else:
        empty_message = ""

    initial_state = json.dumps({
        "insurer": insurer,
        "service": service,
        "province": province,
        "city": city,
    }, ensure_ascii=False)

    html = f"""<!doctype html>
<html lang='fa' dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>بانک سراسری مراکز دکترلینک</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f7fb;color:#172033;font-family:Tahoma,Arial,sans-serif}}.wrap{{max-width:1120px;margin:auto;padding:22px 14px 60px}}
.top{{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}}h1{{color:#12213a;margin:0 0 6px;font-size:26px}}.sub{{color:#667085;font-size:12px;line-height:1.9}}.home{{background:#12213a;color:#fff;text-decoration:none;padding:10px 13px;border-radius:10px;font-size:11px}}
.stats{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:18px 0}}.stat,.card,.search{{background:white;border:1px solid #e5e7eb;border-radius:14px;padding:14px}}.stat b{{font-size:22px;color:#12213a;display:block}}.stat span{{font-size:10px;color:#667085}}
.search{{margin-bottom:15px}}.fields{{display:grid;grid-template-columns:1.5fr repeat(5,1fr);gap:8px}}input,select,button{{width:100%;min-height:43px;border:1px solid #d6dbe4;border-radius:10px;background:#fff;padding:8px 10px;font:inherit;font-size:11px}}button{{background:#1769e0;color:white;border:0;font-weight:800;cursor:pointer;margin-top:8px}}select:disabled{{background:#f2f4f7;color:#98a2b3}}
.meta{{display:flex;justify-content:space-between;gap:10px;color:#667085;font-size:11px;margin:8px 2px 12px}}.grid{{display:grid;gap:10px}}h2{{font-size:16px;margin:0 0 9px;color:#12213a}}p{{margin:5px 0;font-size:12px;line-height:1.9}}.facts{{display:flex;gap:6px 14px;flex-wrap:wrap;font-size:11px;color:#475467}}
.source{{border-top:1px dashed #e5e7eb;margin-top:10px;padding-top:9px;font-size:10px;display:flex;gap:7px;flex-wrap:wrap;align-items:center}}.secondary{{color:#9a6700}}.official{{color:#087443}}a{{color:#2563eb;text-decoration:none}}.notice{{background:#fff8e6;border:1px solid #f5d58a;border-radius:12px;padding:10px;font-size:11px;line-height:1.8;margin-bottom:14px}}.empty{{background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:28px;text-align:center;color:#667085;font-size:12px}}
@media(max-width:900px){{.stats{{grid-template-columns:repeat(3,1fr)}}.fields{{grid-template-columns:1fr 1fr}}}}@media(max-width:520px){{.stats{{grid-template-columns:repeat(2,1fr)}}.fields{{grid-template-columns:1fr}}.top{{display:block}}.home{{display:inline-block;margin-top:8px}}}}
</style></head><body><main class='wrap'>
<div class='top'><div><h1>بانک سراسری مراکز دکترلینک</h1><div class='sub'>جست‌وجو بر اساس بیمه، خدمت/تخصص، استان، شهر و منطقه. فیلترها فقط گزینه‌هایی را نشان می‌دهند که برایشان داده وجود دارد.</div></div><a class='home' href='https://drlinq.ir/'>بازگشت به دکترلینک</a></div>
<div class='stats'><div class='stat'><b>{summary.get('providers',0)}</b><span>مرکز</span></div><div class='stat'><b>{summary.get('locations',0)}</b><span>آدرس</span></div><div class='stat'><b>{summary.get('contracts',0)}</b><span>رابطه بیمه‌ای</span></div><div class='stat'><b>{summary.get('insurers_with_data',0)} / {summary.get('insurers',0)}</b><span>بیمه دارای داده / فهرست</span></div><div class='stat'><b>{summary.get('services',0)}</b><span>خدمت/تخصص</span></div><div class='stat'><b>{summary.get('sources',0)}</b><span>منبع فعال</span></div></div>
<form class='search' method='get' id='searchForm'><div class='fields'>
<input name='q' value='{escape(q,quote=True)}' placeholder='نام مرکز، آدرس یا تلفن'>
<select name='insurer' id='insurer'>{option_html(fs['insurers'], insurer, 'همه بیمه‌های دارای داده')}</select>
<select name='service' id='service'>{option_html(fs['services'], service, 'همه خدمات موجود')}</select>
<select name='province' id='province'>{option_html(fs['provinces'], province, 'همه استان‌های موجود')}</select>
<select name='city' id='city'>{option_html(fs['cities'], city, 'همه شهرهای موجود')}</select>
<input name='district' value='{escape(district,quote=True)}' placeholder='منطقه'>
</div><button type='submit'>جست‌وجو در بانک</button></form>
<div class='notice'>اصل اعتبار: وجود نام یک مرکز در منبع ثانویه به معنی تضمین قرارداد فعال امروز یا پوشش همه خدمات آن مرکز نیست. رکوردهای رسمی و ثانویه جداگانه علامت‌گذاری می‌شوند.</div>
<div class='meta'><span>{len(items)} نتیجه در این صفحه</span><span>حداکثر ۱۰۰ نتیجه نمایش داده می‌شود</span></div>
<div class='grid'>{''.join(cards) if cards else f"<div class='empty'>{escape(empty_message)}</div>"}</div>
</main>
<script>
const initial={initial_state};
const insurer=document.getElementById('insurer');
const service=document.getElementById('service');
const province=document.getElementById('province');
const city=document.getElementById('city');
function refill(el, values, placeholder, preferred=''){{
  const old=preferred || el.value;
  el.innerHTML='';
  const first=document.createElement('option'); first.value=''; first.textContent=placeholder; el.appendChild(first);
  for(const value of values){{ const o=document.createElement('option'); o.value=value; o.textContent=value; if(value===old)o.selected=true; el.appendChild(o); }}
}}
async function refreshFilters(level){{
  const qs=new URLSearchParams();
  if(insurer.value)qs.set('insurer',insurer.value);
  if(service.value)qs.set('service',service.value);
  if(province.value)qs.set('province',province.value);
  try{{
    const r=await fetch('filters?'+qs.toString(),{{headers:{{'Accept':'application/json'}}}});
    if(!r.ok)return;
    const data=await r.json();
    if(level==='insurer'){{ refill(service,data.services,'همه خدمات موجود'); refill(province,data.provinces,'همه استان‌های موجود'); refill(city,data.cities,'همه شهرهای موجود'); }}
    if(level==='service'){{ refill(province,data.provinces,'همه استان‌های موجود'); refill(city,data.cities,'همه شهرهای موجود'); }}
    if(level==='province'){{ refill(city,data.cities,'همه شهرهای موجود'); }}
  }}catch(e){{}}
}}
insurer.addEventListener('change',()=>refreshFilters('insurer'));
service.addEventListener('change',()=>refreshFilters('service'));
province.addEventListener('change',()=>refreshFilters('province'));
</script>
</body></html>"""
    return HTMLResponse(html)
