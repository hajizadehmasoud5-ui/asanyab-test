import hashlib
import json
import os
import re
from datetime import datetime, timezone

import psycopg
import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://iionline.ir/portal/health-authorities-contract"
SOURCE_NAME = "بیمه آنلاین - مراجع درمانی طرف قرارداد بیمه ایران"
INSURER_SLUG = "iran"
INSURER_NAME = "بیمه ایران"


def norm(v: str) -> str:
    v = (v or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    return re.sub(r"\s+", " ", v).strip().lower()


def clean(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "").replace("\xa0", " ")).strip(" -\t\r\n")


def dsn():
    return " ".join([
        f"host={os.environ.get('DB_HOST','postgres')}",
        f"port={os.environ.get('DB_PORT','5432')}",
        f"dbname={os.environ['DB_NAME']}",
        f"user={os.environ['DB_USER']}",
        f"password={os.environ['DB_PASSWORD']}",
    ])


def provider_type(raw: str) -> str:
    n = norm(raw)
    mapping = [
        ("دندان", "dentistry"), ("بيمارستان", "hospital"), ("بیمارستان", "hospital"),
        ("درمانگاه", "clinic"), ("آزمايشگاه", "laboratory"), ("آزمایشگاه", "laboratory"),
        ("داروخانه", "pharmacy"), ("فیزیوتراپی", "physiotherapy"), ("فيزيوتراپي", "physiotherapy"),
        ("راديولوژ", "radiology"), ("رادیولوژ", "radiology"), ("پزشكان", "physician"), ("پزشکان", "physician"),
    ]
    for needle, value in mapping:
        if norm(needle) in n:
            return value
    return "healthcare_provider"


def service_slug_and_name(kind: str, specialty: str):
    k = norm(kind)
    s = norm(specialty)
    joined = f"{k} {s}"
    fixed = [
        (["دندان"], "dentistry", "دندانپزشکی"),
        (["آزمايشگاه", "آزمایشگاه"], "laboratory", "آزمایشگاه"),
        (["داروخانه"], "pharmacy", "داروخانه"),
        (["فیزیوتراپی", "فيزيوتراپي"], "physiotherapy", "فیزیوتراپی"),
        (["mri", "ام آر آی"], "mri", "MRI"),
        (["ct scan", "سی تی", "سي تي"], "ct-scan", "سی تی اسکن"),
        (["سونوگراف"], "ultrasound", "سونوگرافی"),
        (["راديولوژ", "رادیولوژ", "تصويربرداري", "تصویربرداری"], "radiology", "رادیولوژی"),
        (["پزشكي هسته", "پزشکی هسته"], "nuclear-medicine", "پزشکی هسته ای"),
        (["بیمارستان", "بيمارستان"], "hospital", "بیمارستان"),
        (["درمانگاه"], "clinic", "درمانگاه"),
        (["چشم"], "ophthalmology", "چشم پزشکی"),
        (["قلب"], "cardiology", "قلب و عروق"),
        (["داخلي", "داخلی"], "internal-medicine", "متخصص داخلی"),
        (["كودك", "کودک", "اطفال"], "pediatrics", "کودکان"),
        (["زنان", "مامايي", "مامایی"], "obgyn", "زنان و زایمان"),
        (["مغز", "اعصاب"], "neurology", "مغز و اعصاب"),
        (["ارتوپد"], "orthopedics", "ارتوپدی"),
    ]
    for needles, slug, label in fixed:
        if any(norm(x) in joined for x in needles):
            return slug, label
    label = clean(specialty) or clean(kind) or "خدمات درمانی"
    slug = "src-" + hashlib.sha1(norm(label).encode()).hexdigest()[:16]
    return slug, label


def fetch_rows():
    r = requests.get(SOURCE_URL, timeout=45, headers={"User-Agent": "Mozilla/5.0 DrLinqBot/1.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")
    candidates = []
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) >= 5:
            candidates.append((len(rows), table))
    if not candidates:
        raise RuntimeError("No usable HTML table found")
    table = max(candidates, key=lambda x: x[0])[1]
    out = []
    for tr in table.find_all("tr"):
        cells = [clean(x.get_text(" ", strip=True)) for x in tr.find_all(["td", "th"])]
        if len(cells) < 8:
            continue
        if "نام مرجع" in cells[0] or "نوع مرجع" in " ".join(cells):
            continue
        cells += [""] * (13 - len(cells))
        name, kind, specialty, start_date, end_date, province, city, district, phone, admission, address, website, e_intro = cells[:13]
        if not name or not (province or city or address):
            continue
        if name in {"*", "-", "--", "---", "--------------------------", "-----------------------------"}:
            name = clean(kind or specialty or address)
        if not name:
            continue
        out.append({
            "name": name,
            "kind": kind,
            "specialty": specialty,
            "start_date": start_date,
            "end_date": end_date,
            "province": province,
            "city": city,
            "district": district,
            "phone": phone,
            "admission": admission,
            "address": address,
            "website": website,
            "e_intro": e_intro,
        })
    return out


def main():
    rows = fetch_rows()
    now = datetime.now(timezone.utc)
    accepted = rejected = 0
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM bank_insurers WHERE slug=%s", (INSURER_SLUG,))
            insurer = cur.fetchone()
            if not insurer:
                raise RuntimeError("Insurer catalog not seeded")
            insurer_id = insurer[0]
            cur.execute("""INSERT INTO bank_sources(source_type,name,url,insurer_id,authority_rank,last_checked_at)
                VALUES('secondary',%s,%s,%s,60,%s)
                ON CONFLICT(url) DO UPDATE SET last_checked_at=EXCLUDED.last_checked_at, insurer_id=EXCLUDED.insurer_id
                RETURNING id""", (SOURCE_NAME,SOURCE_URL,insurer_id,now))
            source_id = cur.fetchone()[0]
            cur.execute("INSERT INTO bank_ingestion_runs(source_id,status) VALUES(%s,'running') RETURNING id", (source_id,))
            run_id = cur.fetchone()[0]

            for idx, row in enumerate(rows, 1):
                try:
                    naddr = norm(row["address"])
                    cur.execute("""SELECT id FROM bank_locations
                        WHERE province=%s AND city=%s AND district=%s AND normalized_address=%s LIMIT 1""",
                        (row["province"],row["city"],row["district"],naddr))
                    found = cur.fetchone()
                    if found:
                        location_id = found[0]
                    else:
                        cur.execute("""INSERT INTO bank_locations(province,city,district,address,normalized_address,phone)
                            VALUES(%s,%s,%s,%s,%s,%s) RETURNING id""",
                            (row["province"],row["city"],row["district"],row["address"],naddr,row["phone"] or None))
                        location_id = cur.fetchone()[0]

                    pname = clean(row["name"])
                    ptype = provider_type(row["kind"])
                    cur.execute("""SELECT p.id FROM bank_providers p JOIN bank_provider_locations pl ON pl.provider_id=p.id
                        WHERE p.normalized_name=%s AND pl.location_id=%s LIMIT 1""", (norm(pname),location_id))
                    found = cur.fetchone()
                    if found:
                        provider_id = found[0]
                        cur.execute("UPDATE bank_providers SET name=%s, phone=COALESCE(NULLIF(%s,''),phone), updated_at=now() WHERE id=%s",
                                    (pname,row["phone"],provider_id))
                    else:
                        cur.execute("""INSERT INTO bank_providers(provider_type,name,normalized_name,phone,website,metadata)
                            VALUES(%s,%s,%s,%s,%s,%s::jsonb) RETURNING id""",
                            (ptype,pname,norm(pname),row["phone"] or None,row["website"] or None,json.dumps({"source_kind":row["kind"],"specialty":row["specialty"]},ensure_ascii=False)))
                        provider_id = cur.fetchone()[0]
                    cur.execute("INSERT INTO bank_provider_locations(provider_id,location_id,is_primary) VALUES(%s,%s,TRUE) ON CONFLICT DO NOTHING", (provider_id,location_id))

                    slug, label = service_slug_and_name(row["kind"], row["specialty"])
                    cur.execute("""INSERT INTO bank_services(slug,name,normalized_name) VALUES(%s,%s,%s)
                        ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name, normalized_name=EXCLUDED.normalized_name RETURNING id""",
                        (slug,label,norm(label)))
                    service_id = cur.fetchone()[0]
                    cur.execute("""INSERT INTO bank_provider_services(provider_id,service_id,confidence,source_id)
                        VALUES(%s,%s,'source_claimed',%s)
                        ON CONFLICT(provider_id,service_id) DO UPDATE SET source_id=EXCLUDED.source_id""", (provider_id,service_id,source_id))

                    key = hashlib.sha1(f"{pname}|{row['province']}|{row['city']}|{row['address']}".encode()).hexdigest()
                    cur.execute("""INSERT INTO bank_contracts(provider_id,location_id,insurer_id,status,confidence,source_id,source_record_key,last_verified_at)
                        VALUES(%s,%s,%s,'active','secondary',%s,%s,%s)
                        ON CONFLICT(provider_id,location_id,insurer_id,source_id,source_record_key)
                        DO UPDATE SET status='active', confidence='secondary', last_seen_at=now(), last_verified_at=EXCLUDED.last_verified_at""",
                        (provider_id,location_id,insurer_id,source_id,key,now))
                    payload = json.dumps(row, ensure_ascii=False, sort_keys=True)
                    cur.execute("""INSERT INTO bank_raw_records(source_id,source_record_key,payload,payload_hash)
                        VALUES(%s,%s,%s::jsonb,%s) ON CONFLICT(source_id,payload_hash) DO NOTHING""",
                        (source_id,key,payload,hashlib.sha256(payload.encode()).hexdigest()))
                    accepted += 1
                except Exception:
                    rejected += 1

            cur.execute("""UPDATE bank_ingestion_runs SET finished_at=now(),status='success',fetched_count=%s,accepted_count=%s,rejected_count=%s WHERE id=%s""",
                        (len(rows),accepted,rejected,run_id))
            cur.execute("""UPDATE bank_source_registry SET last_success_at=now(), last_error=NULL WHERE slug='iran-online-centers'""")
        conn.commit()
    print(json.dumps({"source":SOURCE_URL,"fetched":len(rows),"accepted":accepted,"rejected":rejected},ensure_ascii=False))

if __name__ == '__main__':
    main()
