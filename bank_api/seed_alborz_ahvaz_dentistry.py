import hashlib
import json
import os
import re
from datetime import datetime, timezone

import psycopg

SOURCE_URL = "https://www.azki.com/blog/alborz-medical-centers/"
SOURCE_NAME = "ازکی - مراکز طرف قرارداد بیمه البرز"
INSURER_SLUG = "alborz"

RECORDS = [
    ("دندانپزشکی احسان رحمانی", "32276563-32276713", "سه راه باهنر ساختمان پزشکان احسان طبقه اول"),
    ("دندانپزشکی پگاه قصری زاده", "09167632008", "اهواز زیتون کارمندی اصلی زیتون بین هدایت و بندر مجتمع کوه نور طبقه 3"),
    ("دندانپزشکی دکتر امید مسجدی", "34430430", "کیانپارس بین 6 و 7 شرقی مجتمع پزشکی دانا طبقه دو"),
    ("دندانپزشکی کلینیک شبانه‌روزی گلستان (دکتر برفر)", "33205062-3", "گلستان خیابان فروردین بین آذر و دی روبروی بانک ملی"),
    ("دندانپزشکی کلینیک عاج", "35516345", "خیابان شریعتی - میدان شریعتی (آخر آسفالت) روبروی مسجد الغدیر"),
    ("دندانپزشکی کلینیک مهرسو", "06134462730", "کوی ملت (کوروش) نبش خیابان 19 اقبال ساختمان ملت طبقه اول"),
    ("دندانپزشکی کلینیک نیلا", "33915690", "کیان آباد بین خیابان 20 و 21 شرقی مجتمع کیان"),
]


def clean(v):
    return re.sub(r"\s+", " ", str(v or "").replace("\xa0", " ")).strip()


def norm(v):
    return clean(v).replace("ي", "ی").replace("ك", "ک").replace("‌", " ").lower()


def dsn():
    return " ".join([
        f"host={os.environ.get('DB_HOST','postgres')}",
        f"port={os.environ.get('DB_PORT','5432')}",
        f"dbname={os.environ['DB_NAME']}",
        f"user={os.environ['DB_USER']}",
        f"password={os.environ['DB_PASSWORD']}",
    ])


def main():
    now = datetime.now(timezone.utc)
    accepted = 0
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM bank_insurers WHERE slug=%s", (INSURER_SLUG,))
            row = cur.fetchone()
            if not row:
                raise RuntimeError("Alborz insurer missing from catalog")
            insurer_id = row[0]

            cur.execute(
                """INSERT INTO bank_sources(source_type,name,url,insurer_id,authority_rank,last_checked_at)
                   VALUES('secondary',%s,%s,%s,60,%s)
                   ON CONFLICT(url) DO UPDATE SET last_checked_at=EXCLUDED.last_checked_at, insurer_id=EXCLUDED.insurer_id
                   RETURNING id""",
                (SOURCE_NAME, SOURCE_URL, insurer_id, now),
            )
            source_id = cur.fetchone()[0]

            cur.execute(
                """INSERT INTO bank_services(slug,name,normalized_name)
                   VALUES('dentistry','دندانپزشکی',%s)
                   ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name, normalized_name=EXCLUDED.normalized_name
                   RETURNING id""",
                (norm("دندانپزشکی"),),
            )
            service_id = cur.fetchone()[0]

            cur.execute("INSERT INTO bank_ingestion_runs(source_id,status) VALUES(%s,'running') RETURNING id", (source_id,))
            run_id = cur.fetchone()[0]

            for i, (name, phone, address) in enumerate(RECORDS, 1):
                naddr = norm(address)
                cur.execute(
                    "SELECT id FROM bank_locations WHERE province=%s AND city=%s AND district='' AND normalized_address=%s LIMIT 1",
                    ("خوزستان", "اهواز", naddr),
                )
                row = cur.fetchone()
                if row:
                    location_id = row[0]
                else:
                    cur.execute(
                        """INSERT INTO bank_locations(province,city,district,address,normalized_address,phone)
                           VALUES(%s,%s,'',%s,%s,%s) RETURNING id""",
                        ("خوزستان", "اهواز", address, naddr, phone or None),
                    )
                    location_id = cur.fetchone()[0]

                cur.execute(
                    """SELECT p.id FROM bank_providers p
                       JOIN bank_provider_locations pl ON pl.provider_id=p.id
                       WHERE p.normalized_name=%s AND pl.location_id=%s LIMIT 1""",
                    (norm(name), location_id),
                )
                row = cur.fetchone()
                if row:
                    provider_id = row[0]
                    cur.execute("UPDATE bank_providers SET phone=COALESCE(NULLIF(%s,''),phone), updated_at=now() WHERE id=%s", (phone, provider_id))
                else:
                    cur.execute(
                        """INSERT INTO bank_providers(provider_type,name,normalized_name,phone)
                           VALUES('dentistry',%s,%s,%s) RETURNING id""",
                        (name, norm(name), phone or None),
                    )
                    provider_id = cur.fetchone()[0]

                cur.execute(
                    "INSERT INTO bank_provider_locations(provider_id,location_id,is_primary) VALUES(%s,%s,TRUE) ON CONFLICT DO NOTHING",
                    (provider_id, location_id),
                )
                cur.execute(
                    """INSERT INTO bank_provider_services(provider_id,service_id,confidence,source_id)
                       VALUES(%s,%s,'source_claimed',%s)
                       ON CONFLICT(provider_id,service_id) DO UPDATE SET source_id=EXCLUDED.source_id""",
                    (provider_id, service_id, source_id),
                )

                key = f"azki-alborz-ahvaz-dentistry-{i}"
                cur.execute(
                    """INSERT INTO bank_contracts(provider_id,location_id,insurer_id,status,confidence,source_id,source_record_key,last_verified_at)
                       VALUES(%s,%s,%s,'active','secondary',%s,%s,%s)
                       ON CONFLICT(provider_id,location_id,insurer_id,source_id,source_record_key)
                       DO UPDATE SET status='active',confidence='secondary',last_seen_at=now(),last_verified_at=EXCLUDED.last_verified_at""",
                    (provider_id, location_id, insurer_id, source_id, key, now),
                )

                payload = json.dumps({
                    "provider": name,
                    "phone": phone,
                    "address": address,
                    "province": "خوزستان",
                    "city": "اهواز",
                    "service": "دندانپزشکی",
                    "insurer": "بیمه البرز",
                    "source": SOURCE_URL,
                }, ensure_ascii=False, sort_keys=True)
                cur.execute(
                    """INSERT INTO bank_raw_records(source_id,source_record_key,payload,payload_hash)
                       VALUES(%s,%s,%s::jsonb,%s) ON CONFLICT(source_id,payload_hash) DO NOTHING""",
                    (source_id, key, payload, hashlib.sha256(payload.encode()).hexdigest()),
                )
                accepted += 1

            cur.execute(
                "UPDATE bank_ingestion_runs SET finished_at=now(),status='success',fetched_count=%s,accepted_count=%s,rejected_count=0 WHERE id=%s",
                (len(RECORDS), accepted, run_id),
            )
        conn.commit()
    print(json.dumps({"ok": True, "accepted": accepted, "insurer": "بیمه البرز", "service": "دندانپزشکی", "city": "اهواز"}, ensure_ascii=False))


if __name__ == '__main__':
    main()
