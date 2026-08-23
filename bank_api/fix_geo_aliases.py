import json
import os

import psycopg

ALIASES = {
    "چهارمحال و بختیاری": [
        "چهارمحال بختیاری",
        "چهارمحال وبختیاری",
    ],
    "کهگیلویه و بویراحمد": [
        "کهکیلویه و بویراحمد",
        "کهکیلویه وبویراحمد",
        "کهگیلویه وبویراحمد",
    ],
}


def dsn():
    return " ".join([
        f"host={os.environ.get('DB_HOST','postgres')}",
        f"port={os.environ.get('DB_PORT','5432')}",
        f"dbname={os.environ['DB_NAME']}",
        f"user={os.environ['DB_USER']}",
        f"password={os.environ['DB_PASSWORD']}",
    ])


def main():
    changed = 0
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            for canonical, variants in ALIASES.items():
                cur.execute(
                    "UPDATE bank_locations SET province=%s, updated_at=now() WHERE province = ANY(%s)",
                    (canonical, variants),
                )
                changed += cur.rowcount
        conn.commit()
    print(json.dumps({"ok": True, "province_aliases_changed": changed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
