import os
import re
import psycopg

# Only infer a neighborhood when its name is explicitly present in the address.
# This avoids inventing geographic data.
AHVAZ_DISTRICTS = [
    ("کیانپارس", ["کیانپارس", "كيانپارس"]),
    ("کیان‌آباد", ["کیان آباد", "کیان‌آباد", "كيان آباد"]),
    ("گلستان", ["گلستان"]),
    ("زیتون کارمندی", ["زیتون کارمندی", "زيتون كارمندي", "زیتون کارمندي"]),
    ("کوی ملت", ["کوی ملت", "کوي ملت", "کوروش", "كوي ملت"]),
    ("امانیه", ["امانیه", "امانيه"]),
    ("پادادشهر", ["پادادشهر", "پاداد شهر"]),
    ("سپیدار", ["سپیدار", "سپيدار"]),
    ("فرهنگ‌شهر", ["فرهنگ شهر", "فرهنگ‌شهر"]),
    ("کوی نفت", ["کوی نفت", "كوي نفت"]),
    ("لشکرآباد", ["لشکرآباد", "لشكرآباد", "لشکر آباد"]),
    ("کمپلو", ["کمپلو", "كمپلو"]),
    ("حصیرآباد", ["حصیرآباد", "حصيرآباد", "حصیر آباد"]),
    ("کوی علوی", ["کوی علوی", "كوي علوي"]),
    ("کیانشهر", ["کیانشهر", "كيانشهر"]),
    ("باهنر", ["باهنر"]),
    ("ملی‌راه", ["ملی راه", "ملی‌راه", "ملي راه"]),
    ("کوی رمضان", ["کوی رمضان", "كوي رمضان"]),
    ("پردیس", ["پردیس", "پرديس"]),
]


def norm(v):
    v=(v or '').replace('ي','ی').replace('ك','ک').replace('\u200c',' ')
    return re.sub(r'\s+',' ',v).strip().lower()


def dsn():
    return ' '.join([
        f"host={os.environ.get('DB_HOST','postgres')}", f"port={os.environ.get('DB_PORT','5432')}",
        f"dbname={os.environ['DB_NAME']}", f"user={os.environ['DB_USER']}", f"password={os.environ['DB_PASSWORD']}"
    ])


def infer(address):
    n=norm(address)
    for canonical, needles in AHVAZ_DISTRICTS:
        if any(norm(x) in n for x in needles):
            return canonical
    return ''


def main():
    updated=0
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id,address FROM bank_locations WHERE city='اهواز' AND COALESCE(district,'')='' AND COALESCE(address,'')<>''")
            for location_id,address in cur.fetchall():
                district=infer(address)
                if district:
                    cur.execute("UPDATE bank_locations SET district=%s,updated_at=now() WHERE id=%s",(district,location_id))
                    updated+=1
        conn.commit()
    print(f'ahvaz_districts_backfilled={updated}')

if __name__=='__main__':
    main()
