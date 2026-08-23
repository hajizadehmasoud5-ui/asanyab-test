import json
import os
import re
from collections import defaultdict

import psycopg
import requests

PROVINCES_URL = "https://raw.githubusercontent.com/babaie774/Iran-geography-data/main/provinces.json"
CITIES_URL = "https://raw.githubusercontent.com/babaie774/Iran-geography-data/main/city.json"

PROVINCE_ALIASES = {
    "آذربایجان شرقی": "آذربایجان شرقی",
    "آذربایجان غربی": "آذربایجان غربی",
    "چهارمحال و بختیاری": "چهارمحال بختیاری",
    "چهارمحال وبختیاری": "چهارمحال بختیاری",
    "کهگیلویه و بویراحمد": "کهکیلویه و بویراحمد",
    "کهگیلویه وبویراحمد": "کهکیلویه و بویراحمد",
    "کهکیلویه وبویراحمد": "کهکیلویه و بویراحمد",
}


def norm(value: str) -> str:
    value = (value or "").replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه")
    value = value.replace("‌", " ").replace("ـ", " ")
    value = re.sub(r"[،,؛;]", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def dsn() -> str:
    return " ".join([
        f"host={os.environ.get('DB_HOST','postgres')}",
        f"port={os.environ.get('DB_PORT','5432')}",
        f"dbname={os.environ['DB_NAME']}",
        f"user={os.environ['DB_USER']}",
        f"password={os.environ['DB_PASSWORD']}",
    ])


def get_json(url: str):
    r = requests.get(url, timeout=40, headers={"User-Agent": "DrLinq/1.0 geography sync"})
    r.raise_for_status()
    return r.json()


def main():
    provinces = get_json(PROVINCES_URL)
    cities = get_json(CITIES_URL)

    province_by_id = {}
    province_by_norm = {}
    cities_by_province = defaultdict(list)
    cities_by_norm = defaultdict(list)

    for p in provinces:
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        point = p.get("point") or {}
        row = {
            "id": int(p["id"]),
            "name": name,
            "norm": norm(name),
            "lat": point.get("latitude"),
            "lon": point.get("longitude"),
        }
        province_by_id[row["id"]] = row
        province_by_norm[row["norm"]] = row

    for alias, canonical in PROVINCE_ALIASES.items():
        target = province_by_norm.get(norm(canonical))
        if target:
            province_by_norm[norm(alias)] = target

    seen_city_keys = set()
    duplicate_city_rows = 0
    for c in cities:
        name = str(c.get("name") or "").strip()
        parent = c.get("parent")
        if not name or parent is None:
            continue
        try:
            province_id = int(parent)
        except Exception:
            continue
        if province_id not in province_by_id:
            continue
        normalized_name = norm(name)
        city_key = (province_id, normalized_name)
        if city_key in seen_city_keys:
            duplicate_city_rows += 1
            continue
        seen_city_keys.add(city_key)
        point = c.get("point") or {}
        row = {
            "source_id": int(c["id"]),
            "province_id": province_id,
            "name": name,
            "norm": normalized_name,
            "lat": point.get("latitude"),
            "lon": point.get("longitude"),
        }
        cities_by_province[province_id].append(row)
        cities_by_norm[row["norm"]].append(row)

    for rows in cities_by_province.values():
        rows.sort(key=lambda x: (-len(x["norm"]), x["norm"]))

    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS geo_provinces (
                  id INTEGER PRIMARY KEY,
                  name TEXT NOT NULL UNIQUE,
                  normalized_name TEXT NOT NULL UNIQUE,
                  latitude DOUBLE PRECISION,
                  longitude DOUBLE PRECISION,
                  source_url TEXT,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)

            for p in province_by_id.values():
                cur.execute(
                    """INSERT INTO geo_provinces(id,name,normalized_name,latitude,longitude,source_url,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,now())
                       ON CONFLICT(id) DO UPDATE SET
                         name=EXCLUDED.name, normalized_name=EXCLUDED.normalized_name,
                         latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
                         source_url=EXCLUDED.source_url, updated_at=now()""",
                    (p["id"], p["name"], p["norm"], p["lat"], p["lon"], PROVINCES_URL),
                )

            # Derived catalog: safe to rebuild on every sync. We intentionally do not trust source IDs as PKs.
            cur.execute("DROP TABLE IF EXISTS geo_cities")
            cur.execute("""
                CREATE TABLE geo_cities (
                  id BIGSERIAL PRIMARY KEY,
                  source_id INTEGER,
                  province_id INTEGER NOT NULL REFERENCES geo_provinces(id) ON DELETE CASCADE,
                  name TEXT NOT NULL,
                  normalized_name TEXT NOT NULL,
                  latitude DOUBLE PRECISION,
                  longitude DOUBLE PRECISION,
                  source_url TEXT,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  UNIQUE(province_id, normalized_name)
                );
                CREATE INDEX idx_geo_cities_province ON geo_cities(province_id, normalized_name);
                CREATE INDEX idx_geo_cities_name ON geo_cities(normalized_name);
            """)

            for rows in cities_by_province.values():
                for c in rows:
                    cur.execute(
                        """INSERT INTO geo_cities(source_id,province_id,name,normalized_name,latitude,longitude,source_url,updated_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,now())
                           ON CONFLICT(province_id, normalized_name) DO NOTHING""",
                        (c["source_id"], c["province_id"], c["name"], c["norm"], c["lat"], c["lon"], CITIES_URL),
                    )

            cur.execute("SELECT id,province,city,address FROM bank_locations")
            locations = cur.fetchall()
            changed = 0
            unresolved = 0

            for location_id, province_raw, city_raw, address_raw in locations:
                p_norm = norm(province_raw)
                c_norm = norm(city_raw)
                address_norm = norm(address_raw)

                province = province_by_norm.get(p_norm) if p_norm else None
                city = None

                if c_norm and province:
                    matches = [x for x in cities_by_norm.get(c_norm, []) if x["province_id"] == province["id"]]
                    if len(matches) == 1:
                        city = matches[0]

                if c_norm and city is None:
                    matches = cities_by_norm.get(c_norm, [])
                    if len(matches) == 1:
                        city = matches[0]
                        province = province_by_id[city["province_id"]]

                if not c_norm and province and address_norm:
                    for candidate in cities_by_province.get(province["id"], []):
                        needle = candidate["norm"]
                        if len(needle) >= 3 and needle in address_norm:
                            city = candidate
                            break

                canonical_province = province["name"] if province else (province_raw or None)
                canonical_city = city["name"] if city else (city_raw or None)

                if canonical_province != province_raw or canonical_city != city_raw:
                    cur.execute(
                        "UPDATE bank_locations SET province=%s, city=%s, updated_at=now() WHERE id=%s",
                        (canonical_province, canonical_city, location_id),
                    )
                    changed += 1

                if not canonical_province or not canonical_city:
                    unresolved += 1

        conn.commit()

    print(json.dumps({
        "ok": True,
        "provinces": len(province_by_id),
        "cities": sum(len(v) for v in cities_by_province.values()),
        "duplicate_city_rows_removed": duplicate_city_rows,
        "locations_changed": changed,
        "locations_unresolved": unresolved,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
