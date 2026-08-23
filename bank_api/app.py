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

app = FastAPI(title="DrLinq Provider Bank", version="0.5.0")
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


SERVICE_JOINS = """
LEFT JOIN bank_provider_services ps ON ps.provider_id=p.id
LEFT JOIN bank_services s ON s.id=ps.service_id
LEFT JOIN bank_service_aliases sa ON sa.normalized_alias=s.normalized_name
LEFT JOIN bank_services canonical ON canonical.id=sa.service_id
"""
SERVICE_NAME_EXPR = "COALESCE(canonical.name, s.name)"
SERVICE_NORM_EXPR = "COALESCE(canonical.normalized_name, s.normalized_name)"


@app.get("/health")
def health():
    with db() as conn:
        value = conn.execute("SELECT 1 AS ok").fetchone()
    return {"ok": bool(value and value["ok"] == 1), "service": "drlinq-bank-api"}


@app.get("/stats")
def stats():
    with db() as conn:
        counts = conn.execute(
            f"""
            SELECT
              (SELECT count(*) FROM bank_providers WHERE active) AS providers,
              (SELECT count(*) FROM bank_locations) AS locations,
              (SELECT count(*) FROM bank_contracts WHERE status='active') AS contracts,
              (SELECT count(*) FROM bank_insurers WHERE active) AS insurers,
              (SELECT count(DISTINCT insurer_id) FROM bank_contracts WHERE status='active') AS insurers_with_data,
              (SELECT count(*) FROM bank_sources WHERE active) AS sources,
              (SELECT count(DISTINCT COALESCE(canonical2.id,s2.id))
                 FROM bank_provider_services ps2
                 JOIN bank_services s2 ON s2.id=ps2.service_id
                 LEFT JOIN bank_service_aliases sa2 ON sa2.normalized_alias=s2.normalized_name
                 LEFT JOIN bank_services canonical2 ON canonical2.id=sa2.service_id) AS services
            """
        ).fetchone()
    return {"counts": counts}


def geography_options(province: str = "", city: str = ""):
    with db() as conn:
        insurers = conn.execute(
            "SELECT name FROM bank_insurers WHERE active ORDER BY name"
        ).fetchall()
        services = conn.execute(
            "SELECT DISTINCT name FROM bank_services WHERE name IS NOT NULL AND name<>'' ORDER BY name"
        ).fetchall()
        provinces = conn.execute(
            """SELECT DISTINCT province FROM bank_locations
               WHERE province IS NOT NULL AND province<>'' ORDER BY province"""
        ).fetchall()

        if province:
            cities = conn.execute(
                """SELECT DISTINCT city FROM bank_locations
                   WHERE province=%s AND city IS NOT NULL AND city<>'' ORDER BY city""",
                (province,),
            ).fetchall()
        else:
            cities = []

        if province and city:
            districts = conn.execute(
                """SELECT DISTINCT district FROM bank_locations
                   WHERE province=%s AND city=%s
                     AND district IS NOT NULL AND district<>'' ORDER BY district""",
                (province, city),
            ).fetchall()
        else:
            districts = []

    return {
        "insurers": [x["name"] for x in insurers],
        "services": [x["name"] for x in services],
        "provinces": [x["province"] for x in provinces],
        "cities": [x["city"] for x in cities],
        "districts": [x["district"] for x in districts],
    }


@app.get("/filters")
def filters(province: str = "", city: str = ""):
    return geography_options(province=province, city=city)


def selection_count(insurer: str = "", service: str = "", province: str = "", city: str = "", district: str = "") -> int:
    clauses = ["c.status='active'", "p.active=TRUE"]
    params = []
    if insurer:
        clauses.append("i.name=%s")
        params.append(insurer)
    if service:
        clauses.append(f"{SERVICE_NORM_EXPR}=%s")
        params.append(norm(service))
    if province:
        clauses.append("l.province=%s")
        params.append(province)
    if city:
        clauses.append("l.city=%s")
        params.append(city)
    if district:
        clauses.append("l.district=%s")
        params.append(district)

    sql = f"""
      SELECT count(DISTINCT p.id) AS n
      FROM bank_contracts c
      JOIN bank_providers p ON p.id=c.provider_id
      JOIN bank_locations l ON l.id=c.location_id
      JOIN bank_insurers i ON i.id=c.insurer_id
      {SERVICE_JOINS}
      WHERE {' AND '.join(clauses)}
    """
    with db() as conn:
        row = conn.execute(sql, params).fetchone()
    return int(row["n"] or 0)


@app.get("/providers")
def providers(
    insurer: str = "",
    service: str = "",
    province: str = "",
    city: str = "",
    district: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    # Kept for backend/future use. The patient-facing page does not expose names, addresses or phones.
    clauses = ["c.status='active'", "p.active=TRUE"]
    params = []
    if insurer:
        clauses.append("i.name=%s")
        params.append(insurer)
    if service:
        clauses.append(f"{SERVICE_NORM_EXPR}=%s")
        params.append(norm(service))
    if province:
        clauses.append("l.province=%s")
        params.append(province)
    if city:
        clauses.append("l.city=%s")
        params.append(city)
    if district:
        clauses.append("l.district=%s")
        params.append(district)

    sql = f"""
      SELECT DISTINCT p.id,p.name,p.provider_type,p.phone,p.website,
        l.province,l.city,l.district,l.address,l.latitude,l.longitude,
        i.name AS insurer,c.confidence,c.last_verified_at,
        src.name AS source_name,src.url AS source_url,src.source_type
      FROM bank_contracts c
      JOIN bank_providers p ON p.id=c.provider_id
      JOIN bank_locations l ON l.id=c.location_id
      JOIN bank_insurers i ON i.id=c.insurer_id
      JOIN bank_sources src ON src.id=c.source_id
      {SERVICE_JOINS}
      WHERE {' AND '.join(clauses)}
      ORDER BY p.name,l.city
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
    service: str = "",
    insurer: str = "",
    province: str = "",
    city: str = "",
    district: str = "",
):
    fs = geography_options(province=province, city=city)
    has_search = bool(service or insurer or province or city or district)
    count = selection_count(
        insurer=insurer, service=service, province=province, city=city, district=district
    ) if has_search else None

    if has_search:
        chosen = " · ".join([x for x in [service, insurer, province, city, district] if x])
        if count:
            result_html = (
                f"<div class='result ok'><b>{count}</b><span>گزینه مطابق انتخاب فعلی در بانک پیدا شد.</span>"
                f"<small>{escape(chosen)}</small></div>"
            )
        else:
            result_html = (
                "<div class='result empty'><b>۰</b><span>در بانک فعلی برای این ترکیب هنوز گزینه ثبت نشده است.</span>"
                f"<small>{escape(chosen)}</small></div>"
            )
    else:
        result_html = ""

    html = f"""<!doctype html>
<html lang='fa' dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>جست‌وجوی درمان دکترلینک</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f7fb;color:#172033;font-family:Tahoma,Arial,sans-serif}}.wrap{{max-width:980px;margin:auto;padding:32px 16px 70px}}
.top{{text-align:center;margin-bottom:26px}}h1{{color:#12213a;margin:0 0 8px;font-size:28px}}.sub{{color:#667085;font-size:13px;line-height:2}}
.search{{background:#fff;border:1px solid #e5e7eb;border-radius:18px;padding:20px;box-shadow:0 8px 28px rgba(16,24,40,.05)}}
.fields{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}}label{{display:block;font-size:11px;color:#667085;margin:0 2px 6px}}select,button{{width:100%;min-height:48px;border:1px solid #d6dbe4;border-radius:12px;background:#fff;padding:9px 10px;font:inherit;font-size:12px}}button{{background:#1769e0;color:white;border:0;font-weight:800;cursor:pointer;margin-top:12px}}select:disabled{{background:#f2f4f7;color:#98a2b3}}
.flow{{display:flex;justify-content:center;gap:7px;flex-wrap:wrap;margin:0 0 18px;color:#667085;font-size:11px}}.flow span{{background:#fff;border:1px solid #e5e7eb;border-radius:999px;padding:7px 10px}}
.result{{margin-top:16px;border-radius:14px;padding:18px;text-align:center;display:grid;gap:6px}}.result b{{font-size:32px}}.result span{{font-size:13px}}.result small{{color:#667085;line-height:1.8}}.result.ok{{background:#ecfdf3;border:1px solid #abefc6;color:#067647}}.result.empty{{background:#fff8e6;border:1px solid #f5d58a;color:#9a6700}}
.note{{color:#667085;text-align:center;font-size:11px;line-height:1.9;margin-top:14px}}
@media(max-width:820px){{.fields{{grid-template-columns:1fr 1fr}}}}@media(max-width:520px){{.fields{{grid-template-columns:1fr}}.wrap{{padding:22px 12px 50px}}h1{{font-size:23px}}}}
</style></head><body><main class='wrap'>
<div class='top'><h1>چه خدمتی می‌خواهی؟</h1><div class='sub'>خدمت و بیمه را انتخاب کن، بعد موقعیتت را از استان تا محله مشخص کن.</div></div>
<div class='flow'><span>۱. خدمت</span><span>۲. بیمه</span><span>۳. استان</span><span>۴. شهر</span><span>۵. محله/منطقه</span></div>
<form class='search' method='get'>
<div class='fields'>
<div><label>خدمت / تخصص</label><select name='service' id='service'>{option_html(fs['services'], service, 'انتخاب خدمت')}</select></div>
<div><label>بیمه</label><select name='insurer' id='insurer'>{option_html(fs['insurers'], insurer, 'انتخاب بیمه')}</select></div>
<div><label>استان</label><select name='province' id='province'>{option_html(fs['provinces'], province, 'انتخاب استان')}</select></div>
<div><label>شهر</label><select name='city' id='city' {'disabled' if not province else ''}>{option_html(fs['cities'], city, 'انتخاب شهر')}</select></div>
<div><label>محله / منطقه</label><select name='district' id='district' {'disabled' if not city else ''}>{option_html(fs['districts'], district, 'انتخاب محله')}</select></div>
</div>
<button type='submit'>بررسی گزینه‌های موجود</button>
{result_html}
</form>
<div class='note'>در این مرحله نام مرکز، آدرس و تلفن به بیمار نمایش داده نمی‌شود. جزئیات مرکز در مرحله بعدی محصول اضافه خواهد شد.</div>
</main>
<script>
const province=document.getElementById('province');
const city=document.getElementById('city');
const district=document.getElementById('district');
function refill(el,values,placeholder){{el.innerHTML='';const f=document.createElement('option');f.value='';f.textContent=placeholder;el.appendChild(f);for(const v of values){{const o=document.createElement('option');o.value=v;o.textContent=v;el.appendChild(o);}}}}
async function loadGeo(){{
  const qs=new URLSearchParams(); if(province.value)qs.set('province',province.value); if(city.value)qs.set('city',city.value);
  try{{const r=await fetch('filters?'+qs.toString());if(!r.ok)return;const d=await r.json();
    if(province.value){{refill(city,d.cities,'انتخاب شهر');city.disabled=false;}}else{{refill(city,[],'انتخاب شهر');city.disabled=true;}}
    refill(district,[],'انتخاب محله');district.disabled=true;
  }}catch(e){{}}
}}
async function loadDistricts(){{
  if(!province.value||!city.value){{refill(district,[],'انتخاب محله');district.disabled=true;return;}}
  const qs=new URLSearchParams({{province:province.value,city:city.value}});
  try{{const r=await fetch('filters?'+qs.toString());if(!r.ok)return;const d=await r.json();refill(district,d.districts,'انتخاب محله');district.disabled=d.districts.length===0;}}catch(e){{}}
}}
province.addEventListener('change',loadGeo);city.addEventListener('change',loadDistricts);
</script></body></html>"""
    return HTMLResponse(html)
