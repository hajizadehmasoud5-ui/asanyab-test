from __future__ import annotations

import os
import re
import psycopg

PERSIAN_TO_ASCII = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
ASCII_TO_PERSIAN = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def dsn() -> str:
    return ' '.join([
        f"host={os.environ.get('DB_HOST','postgres')}",
        f"port={os.environ.get('DB_PORT','5432')}",
        f"dbname={os.environ['DB_NAME']}",
        f"user={os.environ['DB_USER']}",
        f"password={os.environ['DB_PASSWORD']}",
    ])


def infer_region(address: str | None) -> str | None:
    if not address:
        return None
    text = str(address).replace('ي','ی').replace('ك','ک')
    ascii_text = text.translate(PERSIAN_TO_ASCII)
    match = re.search(r'منطقه\s*([0-9]{1,2})', ascii_text, flags=re.I)
    if not match:
        match = re.search(r'\bdistrict\s*([0-9]{1,2})\b', ascii_text, flags=re.I)
    if not match:
        return None
    n = int(match.group(1))
    if n < 1 or n > 22:
        return None
    return f"منطقه {str(n).translate(ASCII_TO_PERSIAN)}"


def main() -> None:
    updated = 0
    counts: dict[str, int] = {}
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id,address FROM bank_locations
                   WHERE province='تهران' AND city='تهران'
                     AND COALESCE(district,'')=''
                     AND COALESCE(address,'')<>''"""
            )
            for location_id, address in cur.fetchall():
                region = infer_region(address)
                if not region:
                    continue
                cur.execute(
                    "UPDATE bank_locations SET district=%s,updated_at=now() WHERE id=%s",
                    (region, location_id),
                )
                updated += 1
                counts[region] = counts.get(region, 0) + 1
        conn.commit()
    print({'ok': True, 'updated': updated, 'regions': counts})


if __name__ == '__main__':
    main()
