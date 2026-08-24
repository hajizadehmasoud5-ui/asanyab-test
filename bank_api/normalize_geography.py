import json
import os
import re
from collections import defaultdict

import psycopg
import requests

# The previous source exposed only ~399 usable cities. This maintained dataset
# contains the nationwide province/city catalogue and is based on Iran's
# administrative-division files. We use the filtered city distribution to avoid
# synthetic numbered rows such as "اراک 1" while still unioning any real provider
# city already present in DrLinq at query time (app_geo.py).
PROVINCES_URL = "https://raw.githubusercontent.com/sajaddp/list-of-cities-in-Iran/main/dist/json/provinces.json"
CITIES_URL = "https://raw.githubusercontent.com/sajaddp/list-of-cities-in-Iran/main/dist/json/cities-filtered.json"

PROVINCE_ALIASES = {
    "آذربایجان شرقی": "آذربایجان شرقی",
    "آذربایجان غربی": "آذربایجان غربی",
    "چهارمحال بختیاری": "چهارمحال و بختیاری",
    "چهارمحال وبختیاری": "چهارمحال و بختیاری",
    "کهگیلویه بویراحمد": "کهگیلویه و بویراحمد",
    "کهگیلویه وبویراحمد": "کهگیلویه و بویراحمد",
    "کهکیلویه و بویراحمد": "کهگیلویه و بویراحمد",
    "کهکیلویه وبویراحمد": "کهگیلویه و بویراحمد",
}


def norm(value: str) -> str:
    value = (value or "").replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه")
    value = value.replace("‌", " ").replace("ـ", " ").replace("\u200f", "").replace("\u200e", "")
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
    r = requests.get(url, timeout=60, headers={"User-Agent": "DrLinq/1.0 nationwide geography sync"})
    r.raise_for_status()
    return r.json()


def main():
    raw_provinces = get_json(PROVINCES_URL)
    raw_cities = get_json(CITIES_URL)

    # Use our own compact/stable province ids. Upstream ids are only source ids.
    cleaned_provinces = []
    seen_provinces = set()
    for p in raw_provinces:
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        canonical = PROVINCE_ALIASES.get(name, name)
        key = norm(canonical)
        if key in seen_provinces:
            continue
        seen_provinces.add(key)
        cleaned_provinces.append({
            "source_id": int(p.get("id")),
            "name": canonical,
            "norm": key,
        })

    # deterministic ids 1..31 regardless of upstream numbering
    cleaned_provinces.sort(key=lambda x: x["source_id"])
    province_by_source_id = {}
    province_by_norm = {}
    for idx, p in enumerate(cleaned_provinces, start=1):
        p["id"] = idx
        province_by_source_id[p["source_id"]] = p
        province_by_norm[p["norm"]] = p

    for alias, canonical in PROVINCE_ALIASES.items():
        target = province_by_norm.get(norm(canonical))
        if target:
            province_by_norm[norm(alias)] = target

    cities_by_province = defaultdict(list)
    cities_by_norm = defaultdict(list)
    seen_city_keys = set()
    duplicate_city_rows = 0

    for c in raw_cities:
        name = str(c.get("name") or "").strip()
        source_province_id = c.get("province_id")
        if not name or source_province_id is None:
            continue
        try:
            source_province_id = int(source_province_id)
        except Exception:
            continue
        province = province_by_source_id.get(source_province_id)
        if not province:
            continue

        normalized_name = norm(name)
        if not normalized_name:
            continue
        city_key = (province["id"], normalized_name)
        if city_key in seen_city_keys:
            duplicate_city_rows += 1
            continue
        seen_city_keys.add(city_key)

        row = {
            "source_id": int(c.get("id")) if c.get("id") is not None else None,
            "province_id": province["id"],
            "name": name,
            "norm": normalized_name,
        }
        cities_by_province[province["id"]].append(row)
        cities_by_norm[normalized_name].append(row)

    for rows in cities_by_province.values():
        rows.sort(key=lambda x: (-len(x["norm"]), x["norm"]))

    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            # Rebuild the canonical geography catalogue; provider rows remain untouched.
            cur.execute("DROP TABLE IF EXISTS geo_cities")
            cur.execute("DROP TABLE IF EXISTS geo_provinces")
            cur.execute("""
                CREATE TABLE geo_provinces (
                  id INTEGER PRIMARY KEY,
                  name TEXT NOT NULL UNIQUE,
                  normalized_name TEXT NOT NULL UNIQUE,
                  latitude DOUBLE PRECISION,
                  longitude DOUBLE PRECISION,
                  source_url TEXT,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE geo_cities (
                  id BIGSERIAL PRIMARY KEY,
                  source_id BIGINT,
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

            for p in cleaned_provinces:
                cur.execute(
                    """INSERT INTO geo_provinces(id,name,normalized_name,source_url,updated_at)
                       VALUES (%s,%s,%s,%s,now())""",
                    (p["id"], p["name"], p["norm"], PROVINCES_URL),
                )

            for rows in cities_by_province.values():
                for c in rows:
                    cur.execute(
                        """INSERT INTO geo_cities(source_id,province_id,name,normalized_name,source_url,updated_at)
                           VALUES (%s,%s,%s,%s,%s,now())
                           ON CONFLICT(province_id, normalized_name) DO NOTHING""",
                        (c["source_id"], c["province_id"], c["name"], c["norm"], CITIES_URL),
                    )

            # Normalize every provider location against the canonical catalogue.
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
                        province = next((p for p in cleaned_provinces if p["id"] == city["province_id"]), province)

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
        "provinces": len(cleaned_provinces),
        "cities": sum(len(v) for v in cities_by_province.values()),
        "duplicate_city_rows_removed": duplicate_city_rows,
        "locations_changed": changed,
        "locations_unresolved": unresolved,
        "province_source": PROVINCES_URL,
        "city_source": CITIES_URL,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
