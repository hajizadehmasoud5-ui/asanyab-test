import os
import psycopg


def dsn():
    return " ".join([
        f"host={os.environ.get('DB_HOST','postgres')}", f"port={os.environ.get('DB_PORT','5432')}",
        f"dbname={os.environ['DB_NAME']}", f"user={os.environ['DB_USER']}", f"password={os.environ['DB_PASSWORD']}"
    ])


def main():
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM bank_insurers WHERE slug='day'")
            new_row=cur.fetchone()
            cur.execute("SELECT id FROM bank_insurers WHERE slug='day-insurance'")
            old_row=cur.fetchone()
            if new_row and old_row and new_row[0] != old_row[0]:
                new_id,old_id=new_row[0],old_row[0]
                # Sources must point at the canonical insurer first.
                cur.execute("UPDATE bank_sources SET insurer_id=%s WHERE insurer_id=%s",(new_id,old_id))
                # Remove old contracts if the same source-record already exists for the canonical insurer.
                cur.execute("""DELETE FROM bank_contracts o USING bank_contracts n
                    WHERE o.insurer_id=%s AND n.insurer_id=%s
                      AND o.provider_id=n.provider_id AND o.location_id=n.location_id
                      AND o.source_id=n.source_id AND o.source_record_key=n.source_record_key""",(old_id,new_id))
                cur.execute("UPDATE bank_contracts SET insurer_id=%s WHERE insurer_id=%s",(new_id,old_id))
                cur.execute("DELETE FROM bank_insurers WHERE id=%s",(old_id,))
        conn.commit()
    print('catalog_cleanup_ok')

if __name__=='__main__':
    main()
