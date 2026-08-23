import hashlib
import json
import os
import re
from datetime import datetime, timezone

import psycopg

SOURCE_URL = "https://www.azki.com/blog/day-insurance-contract-treatment-centers/"
SOURCE_NAME = "Azki - Day Insurance contracted treatment centers"

RECORDS = [
    ("دکتر حمیدرضا علیزاده عطار", "06132236390", "خیابان طالقانی بین شریعتی و مسلم ساختمان سفیر طبقه 4 واحد 10"),
    ("دندانپزشکی دکتر مهدی قشقایی", "06132221023", "خیابان ادهم بین نادری و امام نبش خیابان شمشیری ساختمان فردین طبقه 2"),
    ("مطب دندانپزشکی دکتر مهتاب احمدی", "06133920717", "کیانپارس نبش خیابان سوم شرقی ساختمان پارس طبقه 6"),
    ("نوید عباسی", "06133769767", "کیان آباد نبش خیابان 2 شرقی ساختمان آریا طبقه 3"),
    ("آبان (دندانپزشکی)", "", "گلستان سعدی شیراز شرقی"),
    ("آریاگان", "", "کیان آباد نبش خیابان 4 غربی پلاک 1 طبقه همکف واحد یک"),
    ("دندانپزشکی ابن سینا", "06137666000", "زیتون کارمندی بلوار توحید (زاویه) نبش کمیل درمانگاه بزرگ ابن سینا طبقه 7"),
    ("زرگر", "06133769651", "کیان آباد نبش 4 شرقی مجتمع آمین طبقه دوم"),
    ("شرکت علاج طب سلامت", "", "گلستان خیابان فروردین بین خیابان دی و بهمن پلاک 170"),
    ("فاخر", "", "گلستان خیابان اردیبهشت بین آذر و دی پلاک 191"),
    ("کلینیک دندانپزشکی اکسین", "09217550527", "کیان آباد نبش خیابان 2 مجتمع آریا طبقه پنجم واحد 22"),
    ("کلینیک دندانپزشکی دکتر جواهر فروش", "06133370092", "کیانپارس خیابان 9 غربی فاز 3"),
]


def norm(value: str) -> str:
    value = (value or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def db_dsn() -> str:
    return " ".join([
        f"host={os.environ.get('DB_HOST', 'postgres')}",
        f"port={os.environ.get('DB_PORT', '5432')}",
        f"dbname={os.environ['DB_NAME']}",
        f"user={os.environ['DB_USER']}",
        f"password={os.environ['DB_PASSWORD']}",
    ])


def main():
    now = datetime.now(timezone.utc)
    with psycopg.connect(db_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO bank_insurers(slug,name,normalized_name,official_url)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name, normalized_name=EXCLUDED.normalized_name, updated_at=now()
                   RETURNING id""",
                ("day-insurance", "بیمه دی", norm("بیمه دی"), "https://dayins.ir/"),
            )
            insurer_id = cur.fetchone()[0]

            cur.execute(
                """INSERT INTO bank_sources(source_type,name,url,insurer_id,authority_rank,last_checked_at)
                   VALUES ('secondary',%s,%s,%s,60,%s)
                   ON CONFLICT(url) DO UPDATE SET last_checked_at=EXCLUDED.last_checked_at, insurer_id=EXCLUDED.insurer_id
                   RETURNING id""",
                (SOURCE_NAME, SOURCE_URL, insurer_id, now),
            )
            source_id = cur.fetchone()[0]

            cur.execute(
                """INSERT INTO bank_services(slug,name,normalized_name)
                   VALUES ('dentistry','دندانپزشکی',%s)
                   ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name, normalized_name=EXCLUDED.normalized_name
                   RETURNING id""",
                (norm("دندانپزشکی"),),
            )
            service_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO bank_ingestion_runs(source_id,status) VALUES (%s,'running') RETURNING id",
                (source_id,),
            )
            run_id = cur.fetchone()[0]

            accepted = 0
            for index, (name, phone, address) in enumerate(RECORDS, start=1):
                n_name = norm(name)
                n_address = norm(address)
                cur.execute(
                    "SELECT id FROM bank_locations WHERE province=%s AND city=%s AND normalized_address=%s LIMIT 1",
                    ("خوزستان", "اهواز", n_address),
                )
                row = cur.fetchone()
                if row:
                    location_id = row[0]
                else:
                    cur.execute(
                        """INSERT INTO bank_locations(province,city,address,normalized_address,phone)
                           VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                        ("خوزستان", "اهواز", address, n_address, phone or None),
                    )
                    location_id = cur.fetchone()[0]

                cur.execute(
                    """SELECT p.id FROM bank_providers p
                       JOIN bank_provider_locations pl ON pl.provider_id=p.id
                       WHERE p.normalized_name=%s AND pl.location_id=%s LIMIT 1""",
                    (n_name, location_id),
                )
                row = cur.fetchone()
                if row:
                    provider_id = row[0]
                    cur.execute(
                        "UPDATE bank_providers SET name=%s, phone=COALESCE(NULLIF(%s,''),phone), updated_at=now() WHERE id=%s",
                        (name, phone, provider_id),
                    )
                else:
                    cur.execute(
                        """INSERT INTO bank_providers(provider_type,name,normalized_name,phone)
                           VALUES ('dentistry',%s,%s,%s) RETURNING id""",
                        (name, n_name, phone or None),
                    )
                    provider_id = cur.fetchone()[0]

                cur.execute(
                    """INSERT INTO bank_provider_locations(provider_id,location_id,is_primary)
                       VALUES (%s,%s,TRUE) ON CONFLICT DO NOTHING""",
                    (provider_id, location_id),
                )
                cur.execute(
                    """INSERT INTO bank_provider_services(provider_id,service_id,confidence,source_id)
                       VALUES (%s,%s,'source_claimed',%s)
                       ON CONFLICT(provider_id,service_id) DO UPDATE SET source_id=EXCLUDED.source_id""",
                    (provider_id, service_id, source_id),
                )

                key = f"azki-day-ahvaz-dentistry-{index}"
                cur.execute(
                    """INSERT INTO bank_contracts(provider_id,location_id,insurer_id,status,confidence,source_id,source_record_key,last_verified_at)
                       VALUES (%s,%s,%s,'active','secondary',%s,%s,%s)
                       ON CONFLICT(provider_id,location_id,insurer_id,source_id,source_record_key)
                       DO UPDATE SET status='active', confidence='secondary', last_seen_at=now(), last_verified_at=EXCLUDED.last_verified_at""",
                    (provider_id, location_id, insurer_id, source_id, key, now),
                )

                payload = {
                    "insurer": "بیمه دی",
                    "provider": name,
                    "provider_type": "دندانپزشکی",
                    "province": "خوزستان",
                    "city": "اهواز",
                    "address": address,
                    "phone": phone,
                    "source_url": SOURCE_URL,
                    "confidence": "secondary",
                }
                blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                digest = hashlib.sha256(blob.encode()).hexdigest()
                cur.execute(
                    """INSERT INTO bank_raw_records(source_id,source_record_key,payload,payload_hash)
                       VALUES (%s,%s,%s::jsonb,%s) ON CONFLICT(source_id,payload_hash) DO NOTHING""",
                    (source_id, key, blob, digest),
                )
                accepted += 1

            cur.execute(
                """UPDATE bank_ingestion_runs SET finished_at=now(), status='success', fetched_count=%s,
                   accepted_count=%s, rejected_count=0 WHERE id=%s""",
                (len(RECORDS), accepted, run_id),
            )
        conn.commit()
    print(json.dumps({"ok": True, "accepted": accepted, "source": SOURCE_URL}, ensure_ascii=False))


if __name__ == "__main__":
    main()
