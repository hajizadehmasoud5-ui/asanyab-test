import os
import re
import psycopg

ALIASES = {
    'فیزییوتراپی': 'physiotherapy',
    'فيزيوتراپي': 'physiotherapy',
    'فیزیوتراپی': 'physiotherapy',
    'دندنپزشکی': 'dentistry',
    'دندانپزشكي': 'dentistry',
    'دندانپزشکی': 'dentistry',
    'داروخاته': 'pharmacy',
    'داروخانه': 'pharmacy',
    'آزمايشگاه': 'laboratory',
    'آزمایشگاه': 'laboratory',
    'رادیوگرافی فک و صورت': 'dental-radiology',
    'راديوگرافي فک و صورت': 'dental-radiology',
    'متخصص جراحی لثه': 'dental-perio',
    'متخصص جراحي لثه': 'dental-perio',
    'پریودنتولوژی و لثه': 'dental-perio',
    'متخصص استخوان و مفاصل': 'orthopedics',
    'ارتوپدی': 'orthopedics',
    'متخصص پوست ومو': 'dermatology',
    'متخصص پوست و مو': 'dermatology',
    'جراح و متخصص گوش و حلق و بینی': 'ent',
    'جراح و متخصص گوش حلق و بینی': 'ent',
    'فوق تخصص پیوند قرنیه': 'ophthalmology',
    'متخصص چشم': 'ophthalmology',
    'اپتومتریست ( صرفا ویزیت )': 'optometry',
    'اپتومتریست': 'optometry',
    'عینک فروشی/ عینک سازی': 'eyeglasses',
    'عینک سازی': 'eyeglasses',
    'عینک فروشی': 'eyeglasses',
    'پزشكي هسته اي': 'nuclear-medicine',
    'پزشکی هسته ای': 'nuclear-medicine',
    'ام آر آی': 'mri',
    'MRI': 'mri',
    'سی تی اسکن': 'ct-scan',
    'سي تي اسكن': 'ct-scan',
    'متخصص داخلی': 'internal-medicine',
    'متخصص داخلي': 'internal-medicine',
    'قلب و عروق': 'cardiology',
    'مغز و اعصاب': 'neurology',
    'کودکان': 'pediatrics',
    'اطفال': 'pediatrics',
    'زنان و زایمان': 'obgyn',
    'سونوگرافی': 'ultrasound',
    'رادیولوژی': 'radiology',
    'بیمارستان': 'hospital',
    'درمانگاه': 'clinic',
    'پزشک عمومی': 'general-practice',
}


def norm(v):
    v=(v or '').replace('ي','ی').replace('ك','ک').replace('\u200c',' ')
    return re.sub(r'\s+',' ',v).strip().lower()


def dsn():
    return ' '.join([
        f"host={os.environ.get('DB_HOST','postgres')}",f"port={os.environ.get('DB_PORT','5432')}",
        f"dbname={os.environ['DB_NAME']}",f"user={os.environ['DB_USER']}",f"password={os.environ['DB_PASSWORD']}"
    ])


def main():
    merged=0
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            for alias,target_slug in ALIASES.items():
                cur.execute('SELECT id FROM bank_services WHERE slug=%s',(target_slug,))
                target=cur.fetchone()
                if not target:
                    continue
                target_id=target[0]
                cur.execute('SELECT id,slug,name FROM bank_services WHERE normalized_name=%s AND id<>%s',(norm(alias),target_id))
                old_rows=cur.fetchall()
                for old_id,old_slug,old_name in old_rows:
                    cur.execute('''INSERT INTO bank_provider_services(provider_id,service_id,confidence,source_id)
                        SELECT provider_id,%s,confidence,source_id FROM bank_provider_services WHERE service_id=%s
                        ON CONFLICT(provider_id,service_id) DO UPDATE SET
                          confidence=CASE WHEN bank_provider_services.confidence='source_claimed' THEN bank_provider_services.confidence ELSE EXCLUDED.confidence END,
                          source_id=COALESCE(bank_provider_services.source_id,EXCLUDED.source_id)''',(target_id,old_id))
                    cur.execute('DELETE FROM bank_provider_services WHERE service_id=%s',(old_id,))
                    cur.execute('''INSERT INTO bank_contract_services(contract_id,service_id,coverage_status,evidence_text)
                        SELECT contract_id,%s,coverage_status,evidence_text FROM bank_contract_services WHERE service_id=%s
                        ON CONFLICT(contract_id,service_id) DO NOTHING''',(target_id,old_id))
                    cur.execute('DELETE FROM bank_contract_services WHERE service_id=%s',(old_id,))
                    cur.execute('UPDATE bank_services SET parent_id=NULL WHERE parent_id=%s',(old_id,))
                    cur.execute('DELETE FROM bank_services WHERE id=%s',(old_id,))
                    merged+=1
                cur.execute('''INSERT INTO bank_service_aliases(alias,normalized_alias,service_id) VALUES(%s,%s,%s)
                    ON CONFLICT(alias) DO UPDATE SET normalized_alias=EXCLUDED.normalized_alias,service_id=EXCLUDED.service_id''',(alias,norm(alias),target_id))
        conn.commit()
    print(f'service_aliases_merged={merged}')

if __name__=='__main__':
    main()
