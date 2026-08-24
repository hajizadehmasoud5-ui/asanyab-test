import hashlib
import json
import os
import re
from datetime import datetime, timezone
import psycopg

SOURCE_URL = "https://alborzinsurance.ir/MedicalCenters"
SOURCE_NAME = "بیمه البرز | فایل رسمی مراکز طرف قرارداد"
INSURER_SLUG = "alborz"
INSURER_NAME = "بیمه البرز"
ROWS = [{'provider_key': 'alborz:61f512d62518b9f5a1e8', 'name': 'دندانپزشکی دکتر محمد زرگر', 'facility_type': 'دندانپزشکی', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'نبش4شرقی کیان ابادمجتمع امین طبقه دوم', 'phone': '32202630', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'دارد', 'insurance_notes': 'درمانگاه دندانپزشکی شامل (دندانپزشکان عمومی ومتخصص )'}, {'provider_key': 'alborz:7c425db7265336c84162', 'name': 'دندانپزشکی شکرالهی شهرزاد', 'facility_type': 'دندانپزشکی', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'کیان آباد خ چهار شرقی مجتمع آمین طبقه 2', 'phone': '06133769651', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'دارد', 'insurance_notes': 'دندان پزشکی'}, {'provider_key': 'alborz:757be942bbd44cfb2b88', 'name': 'دندانپزشکی دکتر ارسلان رنجبری', 'facility_type': 'دندانپزشکی', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'کیانپارس خیابان مهر شرقی ساختمان ایرانیان طبقه اول', 'phone': '06133731262', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'دارد', 'insurance_notes': 'دندان پزشکی'}, {'provider_key': 'alborz:d7a8bb0ad2c94743bdda', 'name': 'دندانپزشکی دکتر مهدی قشقایی', 'facility_type': 'دندانپزشکی', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'چهار راه نادری - بین خیابان کسری و محمدیان - قبل از ترمینال باهنر - ساختمان پدرام - طبقه اول', 'phone': '32221064', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'ندارد', 'insurance_notes': 'دندان پزشکی'}, {'provider_key': 'alborz:5f51f6c3d0948820f6b0', 'name': 'دندانپزشکی دکتر سمیرا شاه سیاه', 'facility_type': 'دندانپزشکی', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'کیانپارس - خیابان دوم شرقی - ساختمان اداری پزشکی تشریفات - طبقه 7 - واحد 705', 'phone': '33920775', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'دارد', 'insurance_notes': 'دندان پزشکی'}, {'provider_key': 'alborz:64a9ad42234fc3c4b19e', 'name': 'آزمایشگاه دکتر الهام مطوریان', 'facility_type': 'آزمایشگاه', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'کیانپارس - فلکه سوم - نبش میهن شرقی', 'phone': '3337541', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'دارد', 'insurance_notes': 'آزمایشگاه'}, {'provider_key': 'alborz:eb1ff0a0a5b92b25b6fa', 'name': 'آزمایشگاه طب آزمای نور', 'facility_type': 'آزمایشگاه', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'کیانپارس نبش خیابان پنجم غربی برج پزشکی مفاخر طبقه سوم', 'phone': '33385833-33914284', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'دارد', 'insurance_notes': 'آزمایشگاه'}, {'provider_key': 'alborz:432306b07b11595f7dcd', 'name': 'آزمایشگاه پاسارگاد', 'facility_type': 'آزمایشگاه', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'زیتون کارمندی خیابان حجت بین زمزم و زمرد پلاک 176', 'phone': '34425618-34425619', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'دارد', 'insurance_notes': 'آزمایشگاه'}, {'provider_key': 'alborz:19cc1198186230bced50', 'name': 'آزمایشگاه ژنتیک و تشخیص طبی نورژن', 'facility_type': 'آزمایشگاه', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'کیانپارس خیابان پهلوان غربی بین وهابی و خرداد پلاک 144', 'phone': '33399999', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'دارد', 'insurance_notes': 'تشخیص پزشکی و ژنتیک پزشکی'}, {'provider_key': 'alborz:ca21482ad7006eb7a32d', 'name': 'آزمایشگاه ژنتیک و تشخیص طبی نرگس', 'facility_type': 'آزمایشگاه', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'کیانپارس خیابان میهن شرقی پلاک 36', 'phone': '33336681-2', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'دارد', 'insurance_notes': 'تشخیص پزشکی و ژنتیک پزشکی'}, {'provider_key': 'alborz:72a416e04cc9ddcb33ed', 'name': 'داروخانه دکتر رسولی', 'facility_type': 'داروخانه', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'پادادشهر - بلوازجوادالائمه ( ع ) طبقه همکف مجتمع پزشکی پاداد', 'phone': '35716341', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'دارد', 'insurance_notes': 'داروخانه'}, {'provider_key': 'alborz:37f54de0d75290346607', 'name': 'داروخانه دکتر اردشیرزاده', 'facility_type': 'داروخانه', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'گلستان خیابان فروردین نبش آذر', 'phone': '33756044', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'ندارد', 'insurance_notes': 'داروخانه'}, {'provider_key': 'alborz:769d486b12f263735981', 'name': 'داروخانه کمیل ( محمد فرخی )', 'facility_type': 'داروخانه', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'زیتون کارمندی خیابان کمیل نبش زاویه پلاک 2 درمانگاه کمیل', 'phone': '34493113', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'دارد', 'insurance_notes': 'داروخانه'}, {'provider_key': 'alborz:a2a28cfb8b5ed96a05d3', 'name': 'داروخانه دکتر امین تقیان', 'facility_type': 'داروخانه', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'پادادشهر فلکه جواد الائمه جنب پارک محله', 'phone': '35545258', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'دارد', 'insurance_notes': 'داروخانه'}, {'provider_key': 'alborz:6ddb7ce60dbfe8d2adc0', 'name': 'داروخانه امام سجاد (ع) اهواز', 'facility_type': 'داروخانه', 'province': 'خوزستان', 'city': 'اهواز', 'district': '', 'address': 'بیمارستان گلستان داروخانه شبانه روزی دوم دانشکده داروسازی', 'phone': '061-33115852', 'website': '', 'last_checked_at': '2026-08-24T13:30:58+03:30', 'validity_status': 'تأیید رسمی', 'online_referral_letter': 'دارد', 'insurance_notes': 'قرارداد با این داروخانه صرفا جهت استفاده بیمه شدگان بیماری خاص می باشد .'}]

def clean(v):
    return re.sub(r"\s+", " ", str(v or "").replace("\u200f","").replace("\u200e","").replace("\xa0"," ")).strip()

def norm(v):
    return clean(v).replace("ي","ی").replace("ك","ک").replace("‌"," ").lower()

def dsn():
    return " ".join([f"host={os.environ.get('DB_HOST','postgres')}",f"port={os.environ.get('DB_PORT','5432')}",f"dbname={os.environ['DB_NAME']}",f"user={os.environ['DB_USER']}",f"password={os.environ['DB_PASSWORD']}"])

def service_for(ft):
    return {"دندانپزشکی":("dentistry","دندانپزشکی","dentistry"),"آزمایشگاه":("laboratory","آزمایشگاه","laboratory"),"داروخانه":("pharmacy","داروخانه","pharmacy")}[ft]

def parse_dt(v):
    try: return datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except Exception: return datetime.now(timezone.utc)

def main():
    accepted=updated=0
    with psycopg.connect(dsn()) as conn:
      with conn.cursor() as cur:
        cur.execute("""INSERT INTO bank_insurers(slug,name,normalized_name,official_url,active) VALUES(%s,%s,%s,%s,TRUE) ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name,normalized_name=EXCLUDED.normalized_name,official_url=EXCLUDED.official_url,active=TRUE,updated_at=now() RETURNING id""",(INSURER_SLUG,INSURER_NAME,norm(INSURER_NAME),SOURCE_URL)); insurer_id=cur.fetchone()[0]
        checked=max(parse_dt(r['last_checked_at']) for r in ROWS)
        cur.execute("""INSERT INTO bank_sources(source_type,name,url,insurer_id,authority_rank,active,last_checked_at) VALUES('official',%s,%s,%s,100,TRUE,%s) ON CONFLICT(url) DO UPDATE SET name=EXCLUDED.name,insurer_id=EXCLUDED.insurer_id,source_type='official',authority_rank=100,active=TRUE,last_checked_at=EXCLUDED.last_checked_at RETURNING id""",(SOURCE_NAME,SOURCE_URL,insurer_id,checked)); source_id=cur.fetchone()[0]
        cur.execute("INSERT INTO bank_ingestion_runs(source_id,status,fetched_count) VALUES(%s,'running',%s) RETURNING id",(source_id,len(ROWS))); run_id=cur.fetchone()[0]
      conn.commit()
      for row in ROWS:
        with conn.transaction():
          with conn.cursor() as cur:
            name=clean(row['name']); province=clean(row['province']); city=clean(row['city']); district=clean(row['district']); address=clean(row['address']); naddr=norm(address); phone=clean(row['phone']); website=clean(row['website']); key=clean(row['provider_key']); ptype,sname,slug=service_for(row['facility_type']); verified=parse_dt(row['last_checked_at'])
            cur.execute("SELECT id FROM bank_locations WHERE province=%s AND city=%s AND COALESCE(district,'')=%s AND normalized_address=%s LIMIT 1",(province,city,district,naddr)); x=cur.fetchone()
            if x: loc=x[0]
            else:
              cur.execute("INSERT INTO bank_locations(province,city,district,address,normalized_address,phone) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",(province,city,district,address,naddr,phone or None)); loc=cur.fetchone()[0]
            cur.execute("SELECT p.id FROM bank_providers p JOIN bank_provider_locations pl ON pl.provider_id=p.id WHERE p.normalized_name=%s AND pl.location_id=%s LIMIT 1",(norm(name),loc)); x=cur.fetchone()
            meta=json.dumps({"alborz_provider_key":key,"facility_type":row['facility_type'],"online_referral_letter":row['online_referral_letter'],"insurance_notes":row['insurance_notes'],"validity_status":row['validity_status'],"source_checked_at":row['last_checked_at']},ensure_ascii=False)
            if x:
              pid=x[0]; updated+=1; cur.execute("UPDATE bank_providers SET provider_type=%s,name=%s,phone=COALESCE(NULLIF(%s,''),phone),website=COALESCE(NULLIF(%s,''),website),metadata=metadata || %s::jsonb,active=TRUE,updated_at=now() WHERE id=%s",(ptype,name,phone,website,meta,pid))
            else:
              cur.execute("INSERT INTO bank_providers(provider_type,name,normalized_name,phone,website,metadata,active) VALUES(%s,%s,%s,%s,%s,%s::jsonb,TRUE) RETURNING id",(ptype,name,norm(name),phone or None,website or None,meta)); pid=cur.fetchone()[0]
            cur.execute("INSERT INTO bank_provider_locations(provider_id,location_id,is_primary) VALUES(%s,%s,TRUE) ON CONFLICT DO NOTHING",(pid,loc))
            cur.execute("INSERT INTO bank_services(slug,name,normalized_name) VALUES(%s,%s,%s) ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name,normalized_name=EXCLUDED.normalized_name RETURNING id",(slug,sname,norm(sname))); sid=cur.fetchone()[0]
            cur.execute("INSERT INTO bank_provider_services(provider_id,service_id,confidence,source_id) VALUES(%s,%s,'source_claimed',%s) ON CONFLICT(provider_id,service_id) DO NOTHING",(pid,sid,source_id))
            cur.execute("""INSERT INTO bank_contracts(provider_id,location_id,insurer_id,status,confidence,source_id,source_record_key,last_verified_at) VALUES(%s,%s,%s,'active','official',%s,%s,%s) ON CONFLICT(provider_id,location_id,insurer_id,source_id,source_record_key) DO UPDATE SET status='active',confidence='official',last_seen_at=now(),last_verified_at=EXCLUDED.last_verified_at""",(pid,loc,insurer_id,source_id,key,verified))
            payload=json.dumps(row,ensure_ascii=False,sort_keys=True); cur.execute("INSERT INTO bank_raw_records(source_id,source_record_key,payload,payload_hash) VALUES(%s,%s,%s::jsonb,%s) ON CONFLICT(source_id,payload_hash) DO NOTHING",(source_id,key,payload,hashlib.sha256(payload.encode()).hexdigest())); accepted+=1
      conn.commit()
      with conn.cursor() as cur:
        cur.execute("UPDATE bank_ingestion_runs SET finished_at=now(),status='success',accepted_count=%s,updated_count=%s,rejected_count=0 WHERE id=%s",(accepted,updated,run_id))
      conn.commit()
    print(json.dumps({"ok":True,"pilot":True,"records":len(ROWS),"accepted":accepted,"updated_existing":updated,"source":SOURCE_NAME,"checked_at":checked.isoformat()},ensure_ascii=False))

if __name__=='__main__': main()
