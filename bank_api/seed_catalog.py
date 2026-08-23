import os
import re
import psycopg

INSURERS = [
    ("iran", "بیمه ایران", "https://iraninsurance.ir/"),
    ("asia", "بیمه آسیا", "https://www.bimehasia.com/"),
    ("alborz", "بیمه البرز", "https://www.alborzins.com/"),
    ("dana", "بیمه دانا", "https://www.dana-insurance.ir/"),
    ("parsian", "بیمه پارسیان", "https://parsianinsurance.ir/"),
    ("razi", "بیمه رازی", "https://razi24.ir/"),
    ("karafarin", "بیمه کارآفرین", "https://karafarininsurance.ir/"),
    ("sina", "بیمه سینا", "https://www.sinainsurance.com/"),
    ("mellat", "بیمه ملت", "https://www.mellatinsurance.com/"),
    ("day", "بیمه دی", "https://dayins.ir/"),
    ("saman", "بیمه سامان", "https://www.si24.ir/"),
    ("novin", "بیمه نوین", "https://novininsurance.com/"),
    ("pasargad", "بیمه پاسارگاد", "https://www.insurancepasargad.com/"),
    ("moallem", "بیمه معلم", "https://mic.co.ir/"),
    ("mihan", "بیمه میهن", "https://mihaninsurance.com/"),
    ("kosar", "بیمه کوثر", "https://www.kins.ir/"),
    ("ma", "بیمه ما", "https://bimehma.com/"),
    ("arman", "بیمه آرمان", "https://armanins.com/"),
    ("taavon", "بیمه تعاون", "https://taavon-ins.ir/"),
    ("sarmad", "بیمه سرمد", "https://sarmadins.ir/"),
    ("tejarat-no", "بیمه تجارت نو", "https://tejaratnoins.ir/"),
    ("hekmat-saba", "بیمه حکمت صبا", "https://www.hi24.ir/"),
    ("hooshmand-farda", "بیمه هوشمند فردا", ""),
    ("pardis", "بیمه پردیس", ""),
    ("asmari", "بیمه آسماری", "https://asmari-insurance.com/"),
    ("hafez", "بیمه حافظ", "https://hafezinsurance.ir/"),
    ("omid", "بیمه امید", ""),
    ("tamin", "تأمین اجتماعی", "https://www.tamin.ir/"),
    ("salamat", "بیمه سلامت ایران", "https://www.ihio.gov.ir/"),
    ("armed-forces", "بیمه خدمات درمانی نیروهای مسلح", ""),
    ("atieh-sazan", "آتیه سازان حافظ", "https://atiyehsazan.ir/"),
]

SERVICES = [
    ("hospital", "بیمارستان"), ("clinic", "درمانگاه"), ("emergency-noncritical", "اورژانس غیر بحرانی"),
    ("general-practice", "پزشک عمومی"), ("internal-medicine", "متخصص داخلی"), ("cardiology", "قلب و عروق"),
    ("gastroenterology", "گوارش"), ("nephrology", "کلیه و نفرولوژی"), ("urology", "اورولوژی"),
    ("endocrinology", "غدد"), ("rheumatology", "روماتولوژی"), ("pulmonology", "ریه"),
    ("infectious-disease", "بیماری های عفونی"), ("neurology", "مغز و اعصاب"), ("neurosurgery", "جراحی مغز و اعصاب"),
    ("general-surgery", "جراحی عمومی"), ("orthopedics", "ارتوپدی"), ("sports-medicine", "پزشکی ورزشی"),
    ("obgyn", "زنان و زایمان"), ("pediatrics", "کودکان"), ("neonatology", "نوزادان"),
    ("dermatology", "پوست و مو"), ("psychiatry", "روانپزشکی"), ("psychology", "روانشناسی"),
    ("ent", "گوش حلق بینی"), ("ophthalmology", "چشم پزشکی"), ("optometry", "اپتومتری و عینک"),
    ("anesthesiology", "بیهوشی"), ("pain-medicine", "درد"), ("oncology", "انکولوژی"),
    ("hematology", "خون و هماتولوژی"), ("radiotherapy", "رادیوتراپی"),
    ("dentistry", "دندانپزشکی"), ("dental-general", "دندانپزشکی عمومی"), ("dental-restorative", "ترمیمی و زیبایی دندان"),
    ("dental-endo", "درمان ریشه"), ("dental-perio", "پریودنتولوژی و لثه"), ("dental-prosth", "پروتز دندان"),
    ("dental-ortho", "ارتودنسی"), ("dental-pedo", "دندانپزشکی کودکان"), ("dental-oral-surgery", "جراحی دهان فک و صورت"),
    ("dental-implant", "ایمپلنت"), ("dental-radiology", "رادیولوژی دهان و فک و صورت"),
    ("laboratory", "آزمایشگاه"), ("pathology", "پاتولوژی"), ("genetics-lab", "آزمایشگاه ژنتیک"),
    ("radiology", "رادیولوژی"), ("ultrasound", "سونوگرافی"), ("mammography", "ماموگرافی"),
    ("ct-scan", "سی تی اسکن"), ("mri", "MRI"), ("nuclear-medicine", "پزشکی هسته ای"),
    ("bone-density", "سنجش تراکم استخوان"), ("pet-scan", "PET Scan"),
    ("physiotherapy", "فیزیوتراپی"), ("occupational-therapy", "کاردرمانی"), ("speech-therapy", "گفتاردرمانی"),
    ("rehabilitation", "توانبخشی"), ("audiometry", "شنوایی سنجی"), ("prosthetics-orthotics", "ارتز و پروتز"),
    ("pharmacy", "داروخانه"), ("home-care", "خدمات درمان در منزل"), ("nursing", "خدمات پرستاری"),
    ("dialysis", "دیالیز"), ("infertility", "ناباروری"), ("ivf", "IVF"),
    ("endoscopy", "آندوسکوپی"), ("colonoscopy", "کولونوسکوپی"), ("echocardiography", "اکوکاردیوگرافی"),
    ("ecg", "نوار قلب"), ("holter", "هولتر"), ("angiography", "آنژیوگرافی"),
    ("sleep-lab", "کلینیک خواب"), ("nutrition", "تغذیه"), ("wound-care", "زخم و پانسمان"),
    ("medical-equipment", "تجهیزات پزشکی"), ("hearing-aid", "سمعک"), ("eyeglasses", "عینک"),
]

ALIASES = {
    "دندانپزشكان": "dentistry", "دندانپزشکان": "dentistry", "دندانپزشك": "dental-general", "دندانپزشک": "dental-general",
    "پزشكان": "general-practice", "پزشکان": "general-practice", "پزشك عمومی": "general-practice", "پزشک عمومی": "general-practice",
    "آزمايشگاه": "laboratory", "آزمایشگاه": "laboratory", "فيزيوتراپي": "physiotherapy", "فیزیوتراپی": "physiotherapy",
    "داروخانه": "pharmacy", "بیمارستان": "hospital", "بيمارستان": "hospital", "درمانگاه": "clinic",
    "راديولوژي وسونوگرافي وتصويربرداري": "radiology", "رادیولوژی و سونوگرافی و تصویربرداری": "radiology",
    "MRI": "mri", "ام آر آی": "mri", "سی تی اسکن": "ct-scan", "CT Scan": "ct-scan",
    "پزشكي هسته اي وسنجش تراكم استخوان": "nuclear-medicine", "پزشکی هسته ای": "nuclear-medicine",
}

SOURCES = [
    ("dana-public-centers", "dana", "بیمه دانا", "سامانه عمومی مراکز دانا", "https://dana1404.ir/centers", "secondary", "discover", True, "صفحه عمومی دارای فیلتر استان/شهر/تخصص؛ منبع رسمی شرکت تأیید نشده"),
    ("iran-online-centers", "iran", "بیمه ایران", "بیمه آنلاین - مراجع درمانی بیمه ایران", "https://iionline.ir/portal/health-authorities-contract", "secondary", "html_table", True, "فهرست گسترده؛ وب‌سایت مستقل مرتبط با بیمه ایران، نه دامنه رسمی شرکت"),
    ("mellat-official-centers", "mellat", "بیمه ملت", "مراکز درمانی طرف قرارداد بیمه ملت", "https://www.mellatinsurance.com/marakez", "official", "discover", True, "دامنه رسمی شرکت؛ نیازمند کشف endpoint داده"),
    ("pasargad-official-centers", "pasargad", "بیمه پاسارگاد", "راهنمای مراکز درمانی بیمه پاسارگاد", "https://www.insurancepasargad.com/service-portal/174-treatment-centers", "official", "discover", True, "دامنه رسمی شرکت؛ لینک‌های بیمارستانی/پاراکلینیکی/دندانپزشکی"),
    ("day-azki-centers", "day", "بیمه دی", "فهرست مراکز بیمه دی - ازکی", "https://www.azki.com/blog/day-insurance-contract-treatment-centers/", "secondary", "article_tables", True, "منبع ثانویه به‌روز؛ برای پوشش موقت تا اتصال منبع رسمی"),
]


def norm(v: str) -> str:
    v = (v or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    return re.sub(r"\s+", " ", v).strip().lower()


def dsn():
    return " ".join([
        f"host={os.environ.get('DB_HOST','postgres')}", f"port={os.environ.get('DB_PORT','5432')}",
        f"dbname={os.environ['DB_NAME']}", f"user={os.environ['DB_USER']}", f"password={os.environ['DB_PASSWORD']}"
    ])


def main():
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            for slug, name, url in INSURERS:
                cur.execute("""INSERT INTO bank_insurers(slug,name,normalized_name,official_url)
                    VALUES(%s,%s,%s,%s) ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name, normalized_name=EXCLUDED.normalized_name,
                    official_url=COALESCE(NULLIF(EXCLUDED.official_url,''),bank_insurers.official_url), updated_at=now()""",
                    (slug,name,norm(name),url or None))
            service_ids = {}
            for slug, name in SERVICES:
                cur.execute("""INSERT INTO bank_services(slug,name,normalized_name) VALUES(%s,%s,%s)
                    ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name, normalized_name=EXCLUDED.normalized_name RETURNING id""",
                    (slug,name,norm(name)))
                service_ids[slug] = cur.fetchone()[0]
            for alias, slug in ALIASES.items():
                sid = service_ids.get(slug)
                if sid:
                    cur.execute("""INSERT INTO bank_service_aliases(alias,normalized_alias,service_id) VALUES(%s,%s,%s)
                        ON CONFLICT(alias) DO UPDATE SET normalized_alias=EXCLUDED.normalized_alias, service_id=EXCLUDED.service_id""",
                        (alias,norm(alias),sid))
            for row in SOURCES:
                cur.execute("""INSERT INTO bank_source_registry(slug,insurer_slug,insurer_name,source_name,source_url,source_type,adapter,enabled,last_discovered_at,notes)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,now(),%s)
                    ON CONFLICT(slug) DO UPDATE SET insurer_slug=EXCLUDED.insurer_slug, insurer_name=EXCLUDED.insurer_name,
                    source_name=EXCLUDED.source_name, source_url=EXCLUDED.source_url, source_type=EXCLUDED.source_type,
                    adapter=EXCLUDED.adapter, enabled=EXCLUDED.enabled, last_discovered_at=now(), notes=EXCLUDED.notes""", row)
        conn.commit()
    print(f"insurers={len(INSURERS)} services={len(SERVICES)} aliases={len(ALIASES)} sources={len(SOURCES)}")

if __name__ == '__main__':
    main()
