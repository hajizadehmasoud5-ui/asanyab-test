import hashlib
import json
import os
import re
from datetime import datetime, timezone

import psycopg
import requests

API_URL = "https://dana1404.ir/api/centers"
SOURCE_URL = "https://dana1404.ir/centers"
SOURCE_NAME = "سامانه عمومی مراکز بیمه دانا"
INSURER_SLUG = "dana"


def clean(v):
    return re.sub(r"\s+", " ", str(v or "").replace("\u200f", "").replace("\u200e", "").replace("\xa0", " ")).strip()


def norm(v):
    return clean(v).replace("ي", "ی").replace("ك", "ک").replace("‌", " ").lower()


def dsn():
    return " ".join([
        f"host={os.environ.get('DB_HOST','postgres')}", f"port={os.environ.get('DB_PORT','5432')}",
        f"dbname={os.environ['DB_NAME']}", f"user={os.environ['DB_USER']}", f"password={os.environ['DB_PASSWORD']}"
    ])


def classify(text):
    n=norm(text)
    rules=[
        (["داروخانه"],"pharmacy","داروخانه","pharmacy"),
        (["آزمایشگاه","آزمايشگاه","پاتولوژی","پاتولوژي"],"laboratory","آزمایشگاه","laboratory"),
        (["دندان"],"dentistry","دندانپزشکی","dentistry"),
        (["فیزیوتراپی","فيزيوتراپي"],"physiotherapy","فیزیوتراپی","physiotherapy"),
        (["mri","ام آر آی","ام ار اي"],"radiology","MRI","mri"),
        (["سی تی","سي تي","ct"],"radiology","سی تی اسکن","ct-scan"),
        (["سونوگراف"],"radiology","سونوگرافی","ultrasound"),
        (["رادیولوژ","راديولوژ","تصویربرداری","تصويربرداري"],"radiology","رادیولوژی","radiology"),
        (["قلب"],"physician","قلب و عروق","cardiology"),
        (["کودکان","كودكان","اطفال","نوزاد"],"physician","کودکان","pediatrics"),
        (["کلیه","كليه","نفرولوژ"],"physician","کلیه و نفرولوژی","nephrology"),
        (["اورولوژ","مجاری ادراری","مجاري ادراري","مثانه"],"physician","اورولوژی","urology"),
        (["داخلی","داخلي"],"physician","متخصص داخلی","internal-medicine"),
        (["زنان","زایمان","زايمان"],"physician","زنان و زایمان","obgyn"),
        (["چشم"],"physician","چشم پزشکی","ophthalmology"),
        (["ارتوپد"],"physician","ارتوپدی","orthopedics"),
        (["مغز","اعصاب"],"physician","مغز و اعصاب","neurology"),
        (["عمومی","عمومي"],"physician","پزشک عمومی","general-practice"),
        (["بیمارستان","بيمارستان"],"hospital","بیمارستان","hospital"),
        (["درمانگاه"],"clinic","درمانگاه","clinic"),
    ]
    for needles,ptype,label,slug in rules:
        if any(norm(x) in n for x in needles): return ptype,label,slug
    label=clean(text) or "خدمات درمانی"
    return "healthcare_provider",label,"src-"+hashlib.sha1(norm(label).encode()).hexdigest()[:16]


def main():
    r=requests.get(API_URL,timeout=45,headers={"User-Agent":"Mozilla/5.0 DrLinqIngest/1.0","Accept":"application/json"})
    r.raise_for_status()
    data=r.json()
    rows=data.get("centers",[]) if isinstance(data,dict) else data
    now=datetime.now(timezone.utc)
    accepted=rejected=0
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM bank_insurers WHERE slug=%s",(INSURER_SLUG,))
            x=cur.fetchone()
            if not x: raise RuntimeError("Dana insurer missing from catalog")
            insurer_id=x[0]
            cur.execute("""INSERT INTO bank_sources(source_type,name,url,insurer_id,authority_rank,last_checked_at)
                VALUES('secondary',%s,%s,%s,65,%s) ON CONFLICT(url) DO UPDATE SET last_checked_at=EXCLUDED.last_checked_at,insurer_id=EXCLUDED.insurer_id RETURNING id""",
                (SOURCE_NAME,SOURCE_URL,insurer_id,now))
            source_id=cur.fetchone()[0]
            cur.execute("INSERT INTO bank_ingestion_runs(source_id,status) VALUES(%s,'running') RETURNING id",(source_id,))
            run_id=cur.fetchone()[0]
            for row in rows:
                try:
                    name=clean(row.get("center_name")); city=clean(row.get("city")); province=clean(row.get("province")); address=clean(row.get("address")); phone=clean(row.get("phone")); specialty=clean(row.get("specialty_type"))
                    if not name: raise ValueError("missing center_name")
                    naddr=norm(address)
                    cur.execute("SELECT id FROM bank_locations WHERE province=%s AND city=%s AND district='' AND normalized_address=%s LIMIT 1",(province,city,naddr))
                    f=cur.fetchone()
                    if f: location_id=f[0]
                    else:
                        cur.execute("""INSERT INTO bank_locations(province,city,district,address,normalized_address,phone) VALUES(%s,%s,'',%s,%s,%s) RETURNING id""",(province,city,address,naddr,phone or None))
                        location_id=cur.fetchone()[0]
                    ptype,label,service_slug=classify(specialty)
                    cur.execute("""SELECT p.id FROM bank_providers p JOIN bank_provider_locations pl ON pl.provider_id=p.id WHERE p.normalized_name=%s AND pl.location_id=%s LIMIT 1""",(norm(name),location_id))
                    f=cur.fetchone()
                    if f: provider_id=f[0]
                    else:
                        cur.execute("""INSERT INTO bank_providers(provider_type,name,normalized_name,phone,metadata) VALUES(%s,%s,%s,%s,%s::jsonb) RETURNING id""",(ptype,name,norm(name),phone or None,json.dumps({"computer_code":row.get("computer_code"),"specialty_type":specialty},ensure_ascii=False)))
                        provider_id=cur.fetchone()[0]
                    cur.execute("INSERT INTO bank_provider_locations(provider_id,location_id,is_primary) VALUES(%s,%s,TRUE) ON CONFLICT DO NOTHING",(provider_id,location_id))
                    cur.execute("""INSERT INTO bank_services(slug,name,normalized_name) VALUES(%s,%s,%s) ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name,normalized_name=EXCLUDED.normalized_name RETURNING id""",(service_slug,label,norm(label)))
                    service_id=cur.fetchone()[0]
                    cur.execute("""INSERT INTO bank_provider_services(provider_id,service_id,confidence,source_id) VALUES(%s,%s,'source_claimed',%s) ON CONFLICT(provider_id,service_id) DO UPDATE SET source_id=EXCLUDED.source_id""",(provider_id,service_id,source_id))
                    key=clean(row.get("id")) or hashlib.sha1(f"{name}|{province}|{city}|{address}".encode()).hexdigest()
                    cur.execute("""INSERT INTO bank_contracts(provider_id,location_id,insurer_id,status,confidence,source_id,source_record_key,last_verified_at) VALUES(%s,%s,%s,'active','secondary',%s,%s,%s)
                        ON CONFLICT(provider_id,location_id,insurer_id,source_id,source_record_key) DO UPDATE SET status='active',confidence='secondary',last_seen_at=now(),last_verified_at=EXCLUDED.last_verified_at""",(provider_id,location_id,insurer_id,source_id,key,now))
                    payload=json.dumps(row,ensure_ascii=False,sort_keys=True)
                    cur.execute("""INSERT INTO bank_raw_records(source_id,source_record_key,payload,payload_hash) VALUES(%s,%s,%s::jsonb,%s) ON CONFLICT(source_id,payload_hash) DO NOTHING""",(source_id,key,payload,hashlib.sha256(payload.encode()).hexdigest()))
                    accepted+=1
                except Exception:
                    rejected+=1
            cur.execute("UPDATE bank_ingestion_runs SET finished_at=now(),status='success',fetched_count=%s,accepted_count=%s,rejected_count=%s WHERE id=%s",(len(rows),accepted,rejected,run_id))
            cur.execute("UPDATE bank_source_registry SET adapter='json_api',enabled=TRUE,last_success_at=now(),last_error=NULL WHERE slug='dana-public-centers'")
        conn.commit()
    print(json.dumps({"source":API_URL,"fetched":len(rows),"accepted":accepted,"rejected":rejected},ensure_ascii=False))

if __name__=='__main__': main()
