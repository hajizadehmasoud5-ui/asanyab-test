import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import psycopg
import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.bimehasia.com/%D9%85%D8%B1%D8%A7%DA%A9%D8%B2-%D8%A7%D8%B1%D8%A7%DB%8C%D9%87-%D8%AE%D8%AF%D9%85%D8%A7%D8%AA/%D9%85%D8%B1%D8%A7%D8%AC%D8%B9-%D8%AF%D8%B1%D9%85%D8%A7%D9%86%DB%8C-%D8%B7%D8%B1%D9%81-%D9%82%D8%B1%D8%A7%D8%B1%D8%A7%D8%AF"
# Canonical URL currently used by the site; fallback below fixes the common spelling variant.
SOURCE_URL = SOURCE_URL.replace("%D9%82%D8%B1%D8%A7%D8%B1%D8%A7%D8%AF", "%D9%82%D8%B1%D8%A7%D8%B1%D8%AF%D8%A7%D8%AF")
SOURCE_NAME = "مراجع درمانی طرف قرارداد بیمه آسیا"
INSURER_SLUG = "asia"
PAGER_TARGET = "p$lt$WebPartZone3$zContent$pageplaceholder$p$lt$ctl03$pageplaceholder$p$lt$ctl00$UniPager$pagerElem"


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
        (["دندان"],"dentistry","دندانپزشکی","dentistry"),
        (["داروخانه"],"pharmacy","داروخانه","pharmacy"),
        (["آزمایشگاه","آزمايشگاه","پاتولوژی","پاتولوژي"],"laboratory","آزمایشگاه","laboratory"),
        (["فیزیوتراپی","فيزيوتراپي"],"physiotherapy","فیزیوتراپی","physiotherapy"),
        (["کاردرمانی","كاردرماني"],"rehabilitation","کاردرمانی","occupational-therapy"),
        (["گفتاردرمانی","گفتار درماني"],"rehabilitation","گفتاردرمانی","speech-therapy"),
        (["شنوایی","شنوايي","ادیومتری","اديومتري"],"healthcare_provider","شنوایی سنجی","audiometry"),
        (["mri","ام آر آی","ام ار اي"],"radiology","MRI","mri"),
        (["سی تی","سي تي","ct"],"radiology","سی تی اسکن","ct-scan"),
        (["سونوگراف"],"radiology","سونوگرافی","ultrasound"),
        (["رادیولوژ","راديولوژ","تصویربرداری","تصويربرداري"],"radiology","رادیولوژی","radiology"),
        (["پزشکی هسته","پزشكي هسته"],"radiology","پزشکی هسته ای","nuclear-medicine"),
        (["قلب"],"physician","قلب و عروق","cardiology"),
        (["کودکان","كودكان","اطفال","نوزاد"],"physician","کودکان","pediatrics"),
        (["کلیه","كليه","نفرولوژ"],"physician","کلیه و نفرولوژی","nephrology"),
        (["اورولوژ","مجاری ادراری","مجاري ادراري","مثانه"],"physician","اورولوژی","urology"),
        (["داخلی","داخلي"],"physician","متخصص داخلی","internal-medicine"),
        (["زنان","زایمان","زايمان","مامایی","مامايي"],"physician","زنان و زایمان","obgyn"),
        (["چشم","اپتومت"],"physician","چشم پزشکی","ophthalmology"),
        (["ارتوپد"],"physician","ارتوپدی","orthopedics"),
        (["مغز","اعصاب"],"physician","مغز و اعصاب","neurology"),
        (["پوست"],"physician","پوست و مو","dermatology"),
        (["روانپزش"],"physician","روانپزشکی","psychiatry"),
        (["عمومی","عمومي"],"physician","پزشک عمومی","general-practice"),
        (["بیمارستان","بيمارستان"],"hospital","بیمارستان","hospital"),
        (["درمانگاه","کلینیک","كلينيك"],"clinic","درمانگاه","clinic"),
    ]
    for needles,ptype,label,slug in rules:
        if any(norm(x) in n for x in needles): return ptype,label,slug
    label=clean(text) or "خدمات درمانی"
    return "healthcare_provider",label,"src-"+hashlib.sha1(norm(label).encode()).hexdigest()[:16]


def hidden_fields(soup):
    fields={}
    for inp in soup.select("form input[type=hidden][name]"):
        fields[inp.get("name")]=inp.get("value","")
    return fields


def parse_rows(soup):
    best=[]
    for table in soup.find_all("table"):
        rows=[]
        for tr in table.find_all("tr"):
            cells=[clean(td.get_text(" ",strip=True)) for td in tr.find_all(["td","th"])]
            if len(cells) >= 8:
                rows.append(cells)
        if len(rows) > len(best): best=rows
    out=[]
    for cells in best:
        joined=" ".join(cells)
        if "نام مرجع" in joined and "تخصص" in joined: continue
        cells += [""]*(9-len(cells))
        name,specialty,province,city,address,phone,online_intro,base_insurance,notes=cells[:9]
        if not name or not (province or city or address): continue
        out.append({
            "name":name,"specialty":specialty,"province":province,"city":city,"address":address,"phone":phone,
            "online_intro":online_intro,"base_insurance":base_insurance,"notes":notes,
        })
    return out


def max_page(soup):
    pages=[]
    for a in soup.find_all("a",href=True):
        href=a.get("href","")
        m=re.search(r"__doPostBack\([^,]+,&#39;(\d+)&#39;\)",href)
        if not m:
            m=re.search(r"__doPostBack\([^,]+,'(\d+)'\)",href)
        if m: pages.append(int(m.group(1)))
    # The last-page control can expose the real max page even when only a few page links are visible.
    return max(pages) if pages else 1


def store_rows(conn, source_id, insurer_id, rows, page_no, now):
    accepted=rejected=0
    with conn.cursor() as cur:
        for idx,row in enumerate(rows,1):
            try:
                name=clean(row["name"]); province=clean(row["province"]); city=clean(row["city"]); address=clean(row["address"]); phone=clean(row["phone"]); specialty=clean(row["specialty"])
                naddr=norm(address)
                cur.execute("SELECT id FROM bank_locations WHERE province=%s AND city=%s AND district='' AND normalized_address=%s LIMIT 1",(province,city,naddr))
                f=cur.fetchone()
                if f: location_id=f[0]
                else:
                    cur.execute("INSERT INTO bank_locations(province,city,district,address,normalized_address,phone) VALUES(%s,%s,'',%s,%s,%s) RETURNING id",(province,city,address,naddr,phone or None))
                    location_id=cur.fetchone()[0]
                ptype,label,service_slug=classify(specialty)
                cur.execute("SELECT p.id FROM bank_providers p JOIN bank_provider_locations pl ON pl.provider_id=p.id WHERE p.normalized_name=%s AND pl.location_id=%s LIMIT 1",(norm(name),location_id))
                f=cur.fetchone()
                if f:
                    provider_id=f[0]
                    cur.execute("UPDATE bank_providers SET name=%s,phone=COALESCE(NULLIF(%s,''),phone),updated_at=now() WHERE id=%s",(name,phone,provider_id))
                else:
                    cur.execute("INSERT INTO bank_providers(provider_type,name,normalized_name,phone,metadata) VALUES(%s,%s,%s,%s,%s::jsonb) RETURNING id",(ptype,name,norm(name),phone or None,json.dumps({"specialty":specialty,"online_intro":row['online_intro'],"base_insurance":row['base_insurance'],"notes":row['notes']},ensure_ascii=False)))
                    provider_id=cur.fetchone()[0]
                cur.execute("INSERT INTO bank_provider_locations(provider_id,location_id,is_primary) VALUES(%s,%s,TRUE) ON CONFLICT DO NOTHING",(provider_id,location_id))
                cur.execute("INSERT INTO bank_services(slug,name,normalized_name) VALUES(%s,%s,%s) ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name,normalized_name=EXCLUDED.normalized_name RETURNING id",(service_slug,label,norm(label)))
                service_id=cur.fetchone()[0]
                cur.execute("INSERT INTO bank_provider_services(provider_id,service_id,confidence,source_id) VALUES(%s,%s,'source_claimed',%s) ON CONFLICT(provider_id,service_id) DO UPDATE SET source_id=EXCLUDED.source_id",(provider_id,service_id,source_id))
                key=hashlib.sha1(f"asia|{name}|{province}|{city}|{address}|{specialty}".encode()).hexdigest()
                cur.execute("""INSERT INTO bank_contracts(provider_id,location_id,insurer_id,status,confidence,source_id,source_record_key,last_verified_at)
                    VALUES(%s,%s,%s,'active','official',%s,%s,%s)
                    ON CONFLICT(provider_id,location_id,insurer_id,source_id,source_record_key)
                    DO UPDATE SET status='active',confidence='official',last_seen_at=now(),last_verified_at=EXCLUDED.last_verified_at""",(provider_id,location_id,insurer_id,source_id,key,now))
                payload=json.dumps({**row,"page":page_no},ensure_ascii=False,sort_keys=True)
                cur.execute("INSERT INTO bank_raw_records(source_id,source_record_key,payload,payload_hash) VALUES(%s,%s,%s::jsonb,%s) ON CONFLICT(source_id,payload_hash) DO NOTHING",(source_id,key,payload,hashlib.sha256(payload.encode()).hexdigest()))
                accepted+=1
            except Exception:
                rejected+=1
    return accepted,rejected


def main():
    session=requests.Session()
    session.headers.update({"User-Agent":"Mozilla/5.0 DrLinqIngest/1.0","Accept-Language":"fa-IR,fa;q=0.9,en;q=0.5"})
    r=session.get(SOURCE_URL,timeout=45); r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    total_pages=max_page(soup)
    first_rows=parse_rows(soup)
    if not first_rows: raise RuntimeError("No treatment-center rows found on Asia page 1")
    now=datetime.now(timezone.utc)
    total_fetched=total_accepted=total_rejected=0
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM bank_insurers WHERE slug=%s",(INSURER_SLUG,)); insurer_id=cur.fetchone()[0]
            cur.execute("""INSERT INTO bank_sources(source_type,name,url,insurer_id,authority_rank,last_checked_at)
                VALUES('official',%s,%s,%s,100,%s) ON CONFLICT(url) DO UPDATE SET last_checked_at=EXCLUDED.last_checked_at,insurer_id=EXCLUDED.insurer_id,source_type='official',authority_rank=100 RETURNING id""",(SOURCE_NAME,SOURCE_URL,insurer_id,now))
            source_id=cur.fetchone()[0]
            cur.execute("INSERT INTO bank_ingestion_runs(source_id,status) VALUES(%s,'running') RETURNING id",(source_id,)); run_id=cur.fetchone()[0]
        a,rj=store_rows(conn,source_id,insurer_id,first_rows,1,now); total_fetched+=len(first_rows); total_accepted+=a; total_rejected+=rj; conn.commit()

        current_soup=soup
        for page in range(2,total_pages+1):
            fields=hidden_fields(current_soup)
            fields["__EVENTTARGET"]=PAGER_TARGET
            fields["__EVENTARGUMENT"]=str(page)
            resp=session.post(SOURCE_URL,data=fields,timeout=45); resp.raise_for_status()
            current_soup=BeautifulSoup(resp.text,"html.parser")
            rows=parse_rows(current_soup)
            if not rows:
                raise RuntimeError(f"No rows on Asia page {page}")
            a,rj=store_rows(conn,source_id,insurer_id,rows,page,now)
            total_fetched+=len(rows); total_accepted+=a; total_rejected+=rj
            if page % 10 == 0:
                conn.commit()
                print(json.dumps({"page":page,"pages":total_pages,"fetched":total_fetched,"accepted":total_accepted,"rejected":total_rejected},ensure_ascii=False),flush=True)
            time.sleep(0.2)
        with conn.cursor() as cur:
            cur.execute("UPDATE bank_ingestion_runs SET finished_at=now(),status='success',fetched_count=%s,accepted_count=%s,rejected_count=%s WHERE id=%s",(total_fetched,total_accepted,total_rejected,run_id))
            cur.execute("""UPDATE bank_source_registry SET adapter='aspnet_postback',enabled=TRUE,last_success_at=now(),last_error=NULL WHERE insurer_slug='asia'""")
        conn.commit()
    print(json.dumps({"source":SOURCE_URL,"pages":total_pages,"fetched":total_fetched,"accepted":total_accepted,"rejected":total_rejected},ensure_ascii=False))

if __name__=='__main__': main()
