import os
import re
from collections import defaultdict
from contextlib import contextmanager
from html import escape
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI(title="DrLinq Provider Bank", version="0.8.0")
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
    if os.environ.get("SKIP_SCHEMA_INIT") == "1":
        return
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
SERVICE_NORM_EXPR = "COALESCE(canonical.normalized_name, s.normalized_name)"

SERVICE_GROUP_ORDER = [
    "پزشکی",
    "دندانپزشکی",
    "آزمایشگاه و تشخیص",
    "تصویربرداری",
    "توانبخشی",
    "داروخانه و تجهیزات",
    "مراکز و خدمات درمانی",
    "سایر",
]


def service_group(name: str) -> str:
    n = norm(name)

    dental_terms = (
        "دندان", "ارتودن", "ایمپلنت", "درمان ریشه", "پریودنت", "لثه",
        "دهان و فک", "دهان فک", "پروتز دندان",
    )
    if any(x in n for x in dental_terms):
        return "دندانپزشکی"

    imaging_terms = (
        "mri", "ام آر آی", "pet scan", "پت اسکن", "رادیولوژی", "سونوگرافی",
        "سی تی", "ماموگرافی", "تراکم استخوان", "پزشکی هسته", "آنژیوگرافی",
        "اکوکاردیوگرافی",
    )
    if any(x in n for x in imaging_terms):
        return "تصویربرداری"

    diagnostic_terms = (
        "آزمایشگاه", "پاتولوژی", "ژنتیک", "آندوسکوپی", "کولونوسکوپی",
        "نوار قلب", "هولتر", "کلینیک خواب",
    )
    if any(x in n for x in diagnostic_terms):
        return "آزمایشگاه و تشخیص"

    rehab_terms = (
        "فیزیوتراپی", "کاردرمانی", "گفتار", "توانبخشی", "شنوایی سنجی",
        "سمعک", "پزشکی ورزشی",
    )
    if any(x in n for x in rehab_terms):
        return "توانبخشی"

    pharmacy_equipment_terms = (
        "داروخانه", "تجهیزات پزشکی", "ارتز", "عینک", "اپتومتری",
    )
    if any(x in n for x in pharmacy_equipment_terms):
        return "داروخانه و تجهیزات"

    facility_terms = (
        "بیمارستان", "درمانگاه", "مطب", "مراکز سرپایی", "مرکز جراحی محدود",
        "خدمات درمان در منزل", "خدمات پرستاری", "اورژانس غیر بحرانی",
    )
    if any(x in n for x in facility_terms):
        return "مراکز و خدمات درمانی"

    return "پزشکی"


def build_service_groups(values):
    groups = defaultdict(list)
    seen = set()
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        key = norm(value)
        if key in seen:
            continue
        seen.add(key)
        groups[service_group(value)].append(value)

    ordered = {}
    for group_name in SERVICE_GROUP_ORDER:
        items = sorted(groups.get(group_name, []), key=norm)
        if items:
            ordered[group_name] = items
    return ordered


def service_picker_html(values, selected_value: str) -> str:
    groups = build_service_groups(values)
    selected_group = service_group(selected_value) if selected_value else next(iter(groups), "")
    safe_selected = escape(selected_value or "", quote=True)
    label = escape(selected_value or "انتخاب خدمت")

    tabs = []
    panes = []
    for group_name, items in groups.items():
        active = " active" if group_name == selected_group else ""
        safe_group = escape(group_name, quote=True)
        tabs.append(
            f"<button type='button' class='service-category{active}' data-group='{safe_group}'>{escape(group_name)}</button>"
        )
        item_buttons = []
        for value in items:
            safe_value = escape(value, quote=True)
            selected = " selected" if value == selected_value else ""
            item_buttons.append(
                f"<button type='button' class='service-option{selected}' data-service='{safe_value}'>{escape(value)}</button>"
            )
        hidden = "" if group_name == selected_group else " hidden"
        panes.append(
            f"<div class='service-pane{hidden}' data-pane='{safe_group}'>{''.join(item_buttons)}</div>"
        )

    return (
        f"<input type='hidden' name='service' id='service' value='{safe_selected}'>"
        f"<button type='button' class='service-trigger' id='serviceTrigger' aria-expanded='false'>"
        f"<span id='serviceLabel'>{label}</span><span class='chev'>⌄</span></button>"
        f"<div class='service-mega' id='serviceMega' hidden>"
        f"<div class='service-categories'>{''.join(tabs)}</div>"
        f"<div class='service-content'>{''.join(panes)}</div>"
        f"</div>"
    )


@app.get("/health")
def health():
    with db() as conn:
        row = conn.execute("SELECT 1 AS ok").fetchone()
    return {"ok": bool(row and row["ok"] == 1), "service": "drlinq-bank-api"}


@app.get("/stats")
def stats():
    with db() as conn:
        counts = conn.execute(
            """
            SELECT
              (SELECT count(*) FROM bank_providers WHERE active) AS providers,
              (SELECT count(*) FROM bank_contracts WHERE status='active') AS contracts,
              (SELECT count(*) FROM bank_insurers WHERE active) AS insurers
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

    chosen = " · ".join([x for x in [service, insurer, province, city, district] if x])
    if has_search and count:
        result_html = (
            f"<div class='result ok'><strong>{count}</strong>"
            f"<div><b>گزینه مطابق انتخابت پیدا شد</b><small>{escape(chosen)}</small></div></div>"
        )
    elif has_search:
        result_html = (
            "<div class='result empty'><strong>۰</strong>"
            f"<div><b>برای این ترکیب هنوز گزینه‌ای ثبت نشده</b><small>{escape(chosen)}</small></div></div>"
        )
    else:
        result_html = ""

    html = f"""<!doctype html>
<html lang='fa' dir='rtl'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>جست‌وجوی درمان دکترلینک</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font-family:Tahoma,Arial,sans-serif;color:#20314d;background:#eef3f8}}
.hero{{min-height:100vh;background:linear-gradient(180deg,#e8f2fb 0%,#f5f8fb 58%,#eef3f8 100%);padding:34px 18px 70px}}
.shell{{max-width:1180px;margin:0 auto}}
.brand{{display:flex;align-items:center;justify-content:space-between;margin-bottom:54px}}
.logo{{font-size:28px;font-weight:900;color:#1464a8;text-decoration:none}}
.brand-note{{font-size:12px;color:#667085}}
.intro{{text-align:center;margin:0 auto 28px;max-width:760px}}
.intro h1{{font-size:34px;margin:0 0 10px;color:#17365d}}
.intro p{{margin:0;color:#667085;font-size:14px;line-height:2}}
.search-card{{background:#fff;border-radius:16px;box-shadow:0 14px 38px rgba(31,61,90,.16);border:1px solid #dfe8f1;overflow:visible}}
.search-head{{display:flex;align-items:center;gap:8px;padding:14px 18px;border-bottom:3px solid #1b78c8;color:#17365d;font-size:13px;font-weight:800}}
.search-head .dot{{width:10px;height:10px;border-radius:50%;background:#1b78c8}}
.search-row{{display:grid;grid-template-columns:1.35fr 1.05fr 1fr 1fr 1fr 150px;align-items:stretch}}
.field{{position:relative;border-left:1px solid #e4e8ee;padding:11px 15px 10px;min-width:0}}
.field label{{display:block;font-size:10px;color:#7a8797;margin-bottom:5px;white-space:nowrap}}
.field .value{{display:flex;align-items:center;gap:7px;min-height:28px}}
.icon{{font-size:18px;color:#1b78c8;line-height:1}}
select{{width:100%;border:0;outline:0;background:transparent;color:#20314d;font:inherit;font-size:13px;min-width:0;padding:0 0 0 16px;cursor:pointer}}
select:disabled{{color:#98a2b3;cursor:not-allowed}}
.service-trigger{{width:100%;border:0;background:transparent;padding:0;color:#20314d;font:inherit;font-size:13px;cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:10px;text-align:right}}
.service-trigger .chev{{color:#8b98a7;font-size:16px}}
.service-mega{{position:absolute;z-index:50;top:calc(100% + 13px);right:0;width:min(930px,calc(100vw - 48px));background:#fff;border:1px solid #dfe8f1;border-radius:16px;box-shadow:0 22px 52px rgba(31,61,90,.22);padding:14px;display:grid;grid-template-columns:210px 1fr;gap:14px}}
.service-mega[hidden]{{display:none}}
.service-categories{{display:grid;align-content:start;gap:7px;border-left:1px solid #edf1f5;padding-left:12px}}
.service-category{{border:0;background:#f6f8fb;color:#344054;border-radius:10px;padding:11px 12px;font:inherit;font-size:12px;font-weight:800;text-align:right;cursor:pointer}}
.service-category.active{{background:#e9f3ff;color:#1464a8}}
.service-content{{min-height:260px;max-height:420px;overflow:auto;padding:4px}}
.service-pane{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}}
.service-pane.hidden{{display:none}}
.service-option{{border:1px solid #e5eaf0;background:#fff;color:#344054;border-radius:10px;padding:10px 11px;font:inherit;font-size:12px;line-height:1.6;text-align:right;cursor:pointer}}
.service-option:hover,.service-option.selected{{border-color:#82b8e8;background:#f0f7ff;color:#135f9f}}
.search-btn{{border:0;background:#e94545;color:#fff;font:inherit;font-size:15px;font-weight:900;cursor:pointer;min-height:76px;padding:0 20px}}
.search-btn:hover{{background:#d83b3b}}
.result{{margin:18px auto 0;max-width:760px;border-radius:14px;padding:15px 18px;display:flex;align-items:center;gap:14px;background:#fff;border:1px solid #dfe8f1;box-shadow:0 7px 22px rgba(31,61,90,.07)}}
.result strong{{font-size:30px;min-width:48px;text-align:center}}
.result div{{display:grid;gap:4px}}
.result b{{font-size:13px}}
.result small{{font-size:11px;color:#667085;line-height:1.7}}
.result.ok strong,.result.ok b{{color:#087443}}
.result.empty strong,.result.empty b{{color:#9a6700}}
.helper{{text-align:center;color:#7a8797;font-size:11px;margin-top:15px;line-height:1.9}}
@media(max-width:980px){{
  .search-row{{grid-template-columns:1fr 1fr 1fr}}
  .search-btn{{grid-column:1/-1;min-height:54px}}
  .field{{border-bottom:1px solid #e4e8ee}}
  .service-mega{{position:fixed;top:80px;right:18px;left:18px;width:auto;max-height:calc(100vh - 110px);grid-template-columns:180px 1fr}}
  .service-content{{max-height:calc(100vh - 150px)}}
  .service-pane{{grid-template-columns:repeat(2,minmax(0,1fr))}}
}}
@media(max-width:620px){{
  .hero{{padding:22px 12px 50px}}
  .brand{{margin-bottom:34px}}
  .brand-note{{display:none}}
  .intro h1{{font-size:25px}}
  .intro p{{font-size:12px}}
  .search-row{{grid-template-columns:1fr}}
  .field{{border-left:0;border-bottom:1px solid #e4e8ee;padding:13px 15px}}
  .search-btn{{grid-column:auto}}
  .service-mega{{top:62px;right:10px;left:10px;padding:10px;grid-template-columns:1fr;gap:10px}}
  .service-categories{{display:flex;overflow:auto;border-left:0;border-bottom:1px solid #edf1f5;padding:0 0 9px;gap:7px}}
  .service-category{{white-space:nowrap;text-align:center}}
  .service-content{{max-height:calc(100vh - 190px)}}
  .service-pane{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>
<section class='hero'>
<div class='shell'>
  <div class='brand'><a class='logo' href='https://drlinq.ir/'>دکترلینک</a><div class='brand-note'>انتخاب درمان بر اساس شرایط تو</div></div>
  <div class='intro'>
    <h1>خدمت مناسب را نزدیک خودت پیدا کن</h1>
    <p>خدمت و بیمه را انتخاب کن، بعد استان، شهر و محله را مشخص کن.</p>
  </div>

  <form class='search-card' method='get' id='searchForm'>
    <div class='search-head'><span class='dot'></span>جست‌وجوی درمان</div>
    <div class='search-row'>
      <div class='field' id='serviceField'>
        <label>خدمت / تخصص</label>
        <div class='value'><span class='icon'>✚</span>{service_picker_html(fs['services'], service)}</div>
      </div>
      <div class='field'>
        <label>بیمه</label>
        <div class='value'><span class='icon'>▣</span><select name='insurer' id='insurer'>{option_html(fs['insurers'], insurer, 'انتخاب بیمه')}</select></div>
      </div>
      <div class='field'>
        <label>استان</label>
        <div class='value'><span class='icon'>⌖</span><select name='province' id='province'>{option_html(fs['provinces'], province, 'انتخاب استان')}</select></div>
      </div>
      <div class='field'>
        <label>شهر</label>
        <div class='value'><span class='icon'>⌖</span><select name='city' id='city' {'disabled' if not province else ''}>{option_html(fs['cities'], city, 'انتخاب شهر')}</select></div>
      </div>
      <div class='field'>
        <label>محله / منطقه</label>
        <div class='value'><span class='icon'>⌖</span><select name='district' id='district' {'disabled' if not city else ''}>{option_html(fs['districts'], district, 'انتخاب محله')}</select></div>
      </div>
      <button class='search-btn' type='submit'>🔎 جستجو</button>
    </div>
  </form>

  {result_html}
  <div class='helper'>اول سرشاخه خدمت را انتخاب کن؛ بعد تمام تخصص‌های همان شاخه در پنل عریض نمایش داده می‌شوند.</div>
</div>
</section>
<script>
const province=document.getElementById('province');
const city=document.getElementById('city');
const district=document.getElementById('district');
const serviceInput=document.getElementById('service');
const serviceTrigger=document.getElementById('serviceTrigger');
const serviceLabel=document.getElementById('serviceLabel');
const serviceMega=document.getElementById('serviceMega');
const serviceField=document.getElementById('serviceField');

function refill(el,values,placeholder,selected=''){{
  el.innerHTML='';
  const first=document.createElement('option');
  first.value=''; first.textContent=placeholder; el.appendChild(first);
  for(const v of values){{
    const o=document.createElement('option');
    o.value=v; o.textContent=v; if(v===selected)o.selected=true;
    el.appendChild(o);
  }}
}}

function openServices(){{
  serviceMega.hidden=false;
  serviceTrigger.setAttribute('aria-expanded','true');
}}
function closeServices(){{
  serviceMega.hidden=true;
  serviceTrigger.setAttribute('aria-expanded','false');
}}
serviceTrigger.addEventListener('click',(e)=>{{
  e.stopPropagation();
  if(serviceMega.hidden)openServices(); else closeServices();
}});

document.querySelectorAll('.service-category').forEach(btn=>{{
  btn.addEventListener('click',()=>{{
    const group=btn.dataset.group;
    document.querySelectorAll('.service-category').forEach(x=>x.classList.toggle('active',x===btn));
    document.querySelectorAll('.service-pane').forEach(p=>p.classList.toggle('hidden',p.dataset.pane!==group));
  }});
}});

document.querySelectorAll('.service-option').forEach(btn=>{{
  btn.addEventListener('click',()=>{{
    serviceInput.value=btn.dataset.service;
    serviceLabel.textContent=btn.dataset.service;
    document.querySelectorAll('.service-option').forEach(x=>x.classList.toggle('selected',x===btn));
    closeServices();
  }});
}});

document.addEventListener('click',(e)=>{{
  if(!serviceField.contains(e.target) && !serviceMega.contains(e.target))closeServices();
}});
document.addEventListener('keydown',(e)=>{{if(e.key==='Escape')closeServices();}});

async function fetchGeo(p='',c=''){{
  const qs=new URLSearchParams();
  if(p)qs.set('province',p);
  if(c)qs.set('city',c);
  const r=await fetch('filters?'+qs.toString(),{{headers:{{Accept:'application/json'}}}});
  if(!r.ok)throw new Error('filters');
  return r.json();
}}

province.addEventListener('change',async()=>{{
  const p=province.value;
  refill(city,[],'انتخاب شهر');
  refill(district,[],'انتخاب محله');
  city.disabled=true; district.disabled=true;
  if(!p)return;
  try{{
    const d=await fetchGeo(p,'');
    refill(city,d.cities,'انتخاب شهر');
    city.disabled=false;
  }}catch(e){{}}
}});

city.addEventListener('change',async()=>{{
  const p=province.value, c=city.value;
  refill(district,[],'انتخاب محله');
  district.disabled=true;
  if(!p||!c)return;
  try{{
    const d=await fetchGeo(p,c);
    refill(district,d.districts,'انتخاب محله');
    district.disabled=(d.districts||[]).length===0;
  }}catch(e){{}}
}});
</script>
</body>
</html>"""
    return HTMLResponse(html)
