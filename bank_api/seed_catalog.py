import os
import re
import psycopg

INSURERS = [
    ("iran", "بیمه ایران", "https://iraninsurance.ir/"),
    ("asia", "بیمه آسیا", "https://www.bimehasia.com/"),
    ("alborz", "بیمه البرز", "https://alborzinsurance.ir/"),
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
    ("hospital", "بیمارستان"), ("clinic", "درمانگاه"), ("specialty-clinic", "کلینیک تخصصی"),
    ("day-surgery", "مرکز جراحی محدود"), ("urgent-care", "اورژانس سرپایی"), ("home-care", "خدمات درمان در منزل"),
    ("nursing", "خدمات پرستاری"), ("wound-care", "زخم و پانسمان"),
    ("general-practice", "پزشک عمومی"), ("family-medicine", "پزشکی خانواده"), ("occupational-medicine", "طب کار"),
    ("internal-medicine", "متخصص داخلی"), ("cardiology", "قلب و عروق"), ("gastroenterology", "گوارش"),
    ("hepatology", "کبد"), ("nephrology", "کلیه و نفرولوژی"), ("urology", "اورولوژی"),
    ("endocrinology", "غدد"), ("rheumatology", "روماتولوژی"), ("pulmonology", "ریه"),
    ("infectious-disease", "بیماری های عفونی"), ("allergy-immunology", "آلرژی و ایمونولوژی"),
    ("neurology", "مغز و اعصاب"), ("neurosurgery", "جراحی مغز و اعصاب"),
    ("general-surgery", "جراحی عمومی"), ("vascular-surgery", "جراحی عروق"), ("cardiac-surgery", "جراحی قلب"),
    ("thoracic-surgery", "جراحی قفسه سینه"), ("plastic-surgery", "جراحی پلاستیک و ترمیمی"),
    ("pediatric-surgery", "جراحی کودکان"), ("colorectal-surgery", "جراحی کولورکتال"),
    ("orthopedics", "ارتوپدی"), ("hand-surgery", "جراحی دست"), ("sports-medicine", "پزشکی ورزشی"),
    ("pmr", "طب فیزیکی و توانبخشی"), ("obgyn", "زنان و زایمان"), ("gynecology", "زنان"),
    ("midwifery", "مامایی"), ("pediatrics", "کودکان"), ("neonatology", "نوزادان"),
    ("dermatology", "پوست و مو"), ("psychiatry", "روانپزشکی"), ("psychology", "روانشناسی"),
    ("counseling", "مشاوره"), ("ent", "گوش حلق و بینی"), ("ophthalmology", "چشم پزشکی"),
    ("optometry", "اپتومتری"), ("anesthesiology", "بیهوشی"), ("pain-medicine", "کلینیک درد"),
    ("oncology", "انکولوژی"), ("hematology", "خون و هماتولوژی"), ("radiotherapy", "رادیوتراپی"),
    ("medical-genetics", "ژنتیک پزشکی"), ("geriatrics", "طب سالمندی"), ("bariatric", "چاقی و جراحی چاقی"),
    ("breast-clinic", "بیماری های پستان"), ("transplant", "پیوند اعضا"),
    ("dentistry", "دندانپزشکی"), ("dental-general", "دندانپزشکی عمومی"),
    ("dental-restorative", "ترمیمی و زیبایی دندان"), ("dental-endo", "درمان ریشه"),
    ("dental-perio", "پریودنتولوژی و لثه"), ("dental-prosth", "پروتز دندان"),
    ("dental-ortho", "ارتودنسی"), ("dental-pedo", "دندانپزشکی کودکان"),
    ("dental-oral-surgery", "جراحی دهان فک و صورت"), ("dental-oral-medicine", "بیماری های دهان"),
    ("dental-oral-pathology", "آسیب شناسی دهان"), ("dental-implant", "ایمپلنت"),
    ("dental-radiology", "رادیولوژی دهان و فک و صورت"), ("dental-scaling", "جرم گیری دندان"),
    ("dental-filling", "پرکردن دندان"), ("dental-rct", "عصب کشی دندان"),
    ("dental-extraction", "کشیدن دندان"), ("dental-surgical-extraction", "جراحی دندان"),
    ("dental-crown", "روکش دندان"), ("dental-bridge", "بریج دندان"), ("dental-denture", "دندان مصنوعی"),
    ("dental-bleaching", "بلیچینگ دندان"),
    ("laboratory", "آزمایشگاه"), ("pathology", "پاتولوژی"), ("cytology", "سیتولوژی"),
    ("genetics-lab", "آزمایشگاه ژنتیک"), ("molecular-lab", "آزمایشگاه مولکولی و PCR"), ("blood-bank", "بانک خون"),
    ("radiology", "رادیولوژی"), ("ultrasound", "سونوگرافی"), ("mammography", "ماموگرافی"),
    ("ct-scan", "سی تی اسکن"), ("mri", "MRI"), ("nuclear-medicine", "پزشکی هسته ای"),
    ("bone-density", "سنجش تراکم استخوان"), ("pet-scan", "PET Scan"),
    ("ecg", "نوار قلب"), ("echocardiography", "اکوکاردیوگرافی"), ("stress-test", "تست ورزش"),
    ("holter", "هولتر قلب"), ("bp-holter", "هولتر فشار خون"), ("angiography", "آنژیوگرافی"),
    ("electrophysiology", "الکتروفیزیولوژی قلب"), ("eeg", "نوار مغز"), ("emg", "نوار عضله"),
    ("ncv", "نوار عصب"), ("spirometry", "اسپیرومتری"), ("sleep-lab", "کلینیک خواب"),
    ("endoscopy", "آندوسکوپی"), ("colonoscopy", "کولونوسکوپی"), ("ercp", "ERCP"),
    ("dialysis", "دیالیز"), ("chemotherapy", "شیمی درمانی"), ("infusion", "تزریقات و انفوزیون"),
    ("lithotripsy", "سنگ شکنی"), ("infertility", "ناباروری"), ("ivf", "IVF"), ("iui", "IUI"),
    ("physiotherapy", "فیزیوتراپی"), ("occupational-therapy", "کاردرمانی"), ("speech-therapy", "گفتاردرمانی"),
    ("rehabilitation", "توانبخشی"), ("audiometry", "شنوایی سنجی"), ("vestibular-rehab", "توانبخشی تعادل"),
    ("prosthetics-orthotics", "ارتز و پروتز"), ("hydrotherapy", "آب درمانی"),
    ("nutrition", "تغذیه"), ("pharmacy", "داروخانه"), ("medical-equipment", "تجهیزات پزشکی"),
    ("hearing-aid", "سمعک"), ("eyeglasses", "عینک"), ("contact-lens", "لنز طبی"),
]

ALIASES = {
    "دندانپزشكان": "dentistry", "دندانپزشکان": "dentistry", "دندانپزشكي": "dentistry", "دندانپزشکی": "dentistry",
    "دندنپزشکی": "dentistry", "دندانپزشك": "dental-general", "دندانپزشک": "dental-general",
    "پزشكان": "general-practice", "پزشکان": "general-practice", "پزشك عمومی": "general-practice", "پزشک عمومی": "general-practice",
    "آزمايشگاه": "laboratory", "آزمایشگاه": "laboratory", "پاتوبیولوژی": "pathology", "پاتولوژی": "pathology",
    "فيزيوتراپي": "physiotherapy", "فیزیوتراپی": "physiotherapy", "فیزییوتراپی": "physiotherapy",
    "داروخاته": "pharmacy", "داروخانه": "pharmacy", "بیمارستان": "hospital", "بيمارستان": "hospital", "درمانگاه": "clinic",
    "كلينيك": "specialty-clinic", "کلینیک": "specialty-clinic",
    "راديولوژي وسونوگرافي وتصويربرداري": "radiology", "رادیولوژی و سونوگرافی و تصویربرداری": "radiology",
    "MRI": "mri", "ام آر آی": "mri", "ام ار ای": "mri", "سی تی اسکن": "ct-scan", "سي تي اسكن": "ct-scan", "CT Scan": "ct-scan",
    "پزشكي هسته اي وسنجش تراكم استخوان": "nuclear-medicine", "پزشکی هسته ای": "nuclear-medicine",
    "عینک فروشی/ عینک سازی": "eyeglasses", "عینک سازی": "eyeglasses", "عينك سازي": "eyeglasses",
    "اپتومتریست ( صرفا ویزیت )": "optometry", "اپتومتریست": "optometry",
    "متخصص استخوان و مفاصل": "orthopedics", "متخصص پوست ومو": "dermatology", "متخصص پوست و مو": "dermatology",
    "جراح و متخصص گوش و حلق و بینی": "ent", "فوق تخصص پیوند قرنیه": "ophthalmology",
    "متخصص جراحی لثه": "dental-perio", "رادیوگرافی فک و صورت": "dental-radiology",
    "سنگ شكن": "lithotripsy", "سنگ شکن": "lithotripsy", "سنگ شکنی": "lithotripsy",
}

SOURCES = [
    ("asia-official-centers", "asia", "بیمه آسیا", "مراجع درمانی طرف قرارداد بیمه آسیا", "https://www.bimehasia.com/مراکز-ارایه-خدمات/مراجع-درمانی-طرف-قرارداد", "official", "aspnet_postback", True, "منبع رسمی شرکت بیمه آسیا"),
    ("dana-public-centers", "dana", "بیمه دانا", "سامانه عمومی مراکز دانا", "https://dana1404.ir/centers", "secondary", "json_api", True, "صفحه عمومی دارای فیلتر استان/شهر/تخصص؛ دامنه رسمی شرکت دانا تأیید نشده"),
    ("iran-online-centers", "iran", "بیمه ایران", "بیمه آنلاین - مراجع درمانی بیمه ایران", "https://iionline.ir/portal/health-authorities-contract", "secondary", "broken", False, "منبع ثانویه در 2026-08-23 به www ریدایرکت شد و 404 داد؛ تا یافتن منبع جایگزین غیرفعال است"),
    ("mellat-official-centers", "mellat", "بیمه ملت", "مراکز درمانی طرف قرارداد بیمه ملت", "https://www.mellatinsurance.com/marakez", "official", "discover", True, "دامنه رسمی شرکت؛ داده صفحه به شکل پویا بارگذاری می‌شود و endpoint در حال کشف است"),
    ("saman-darmanet-centers", "saman", "بیمه سامان", "سامانه مراکز درمانی درمانت", "https://providers.darmanet.ir/", "official_linked", "discover", True, "سایت رسمی بیمه سامان کاربران را مستقیماً به این سامانه برای مشاهده مراکز طرف قرارداد ارجاع می‌دهد"),
    ("pasargad-official-centers", "pasargad", "بیمه پاسارگاد", "راهنمای مراکز درمانی بیمه پاسارگاد", "https://www.insurancepasargad.com/service-portal/174-treatment-centers", "official", "discover", True, "صفحه رسمی شرکت؛ لینک قدیمی Iran Assistance فعلاً 404 است و داده تا رفع آن قطعی وارد نمی‌شود"),
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
