from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import psycopg

from app import dsn, norm


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def provider_type(record: dict[str, Any], fallback_service: str) -> str:
    value = clean(record.get("facility_type") or record.get("provider_type"))
    if value:
        return value
    n = norm(fallback_service)
    if "دندان" in n:
        return "دندانپزشکی"
    if "آزمایشگاه" in n:
        return "آزمایشگاه"
    return "مرکز درمانی"


def extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("providers"), list):
        return [x for x in payload["providers"] if isinstance(x, dict)]
    result = payload.get("result")
    if isinstance(result, dict) and isinstance(result.get("providers"), list):
        return [x for x in result["providers"] if isinstance(x, dict)]
    return []


def ensure_source(cur, *, name: str, url: str, source_type: str = "discovery"):
    cur.execute(
        """
        INSERT INTO bank_sources(source_type,name,url,authority_rank,active,last_checked_at)
        VALUES (%s,%s,%s,55,TRUE,now())
        ON CONFLICT(url) DO UPDATE SET
          name=EXCLUDED.name,
          source_type=EXCLUDED.source_type,
          active=TRUE,
          last_checked_at=now()
        RETURNING id
        """,
        (source_type, name, url),
    )
    return cur.fetchone()[0]


def ensure_service(cur, name: str):
    normalized = norm(name)
    cur.execute(
        "SELECT id FROM bank_services WHERE normalized_name=%s ORDER BY created_at LIMIT 1",
        (normalized,),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    slug = "discovery-" + hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    cur.execute(
        """
        INSERT INTO bank_services(slug,name,normalized_name)
        VALUES (%s,%s,%s)
        ON CONFLICT(slug) DO UPDATE SET name=EXCLUDED.name, normalized_name=EXCLUDED.normalized_name
        RETURNING id
        """,
        (slug, name, normalized),
    )
    return cur.fetchone()[0]


def find_or_create_location(cur, record: dict[str, Any]):
    province = clean(record.get("province"))
    city = clean(record.get("city"))
    district = clean(record.get("district"))
    address = clean(record.get("address"))
    normalized_address = norm(address or "")
    phone = clean(record.get("phone"))
    lat = record.get("latitude")
    lng = record.get("longitude")

    if address:
        cur.execute(
            """
            SELECT id FROM bank_locations
            WHERE COALESCE(province,'')=COALESCE(%s,'')
              AND COALESCE(city,'')=COALESCE(%s,'')
              AND normalized_address=%s
            LIMIT 1
            """,
            (province, city, normalized_address),
        )
        row = cur.fetchone()
        if row:
            location_id = row[0]
            cur.execute(
                """UPDATE bank_locations SET
                   district=COALESCE(district,%s),
                   phone=COALESCE(phone,%s),
                   latitude=COALESCE(latitude,%s),
                   longitude=COALESCE(longitude,%s),
                   updated_at=now()
                   WHERE id=%s""",
                (district, phone, lat, lng, location_id),
            )
            return location_id

    cur.execute(
        """
        INSERT INTO bank_locations(province,city,district,address,normalized_address,latitude,longitude,phone)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (province, city, district, address, normalized_address, lat, lng, phone),
    )
    return cur.fetchone()[0]


def find_provider(cur, record: dict[str, Any], location_id):
    name = clean(record.get("name"))
    if not name:
        return None
    n_name = norm(name)
    phone = clean(record.get("phone"))
    website = clean(record.get("website"))

    if phone:
        cur.execute(
            """
            SELECT p.id
            FROM bank_providers p
            JOIN bank_provider_locations pl ON pl.provider_id=p.id
            WHERE p.phone=%s AND pl.location_id=%s
            LIMIT 1
            """,
            (phone, location_id),
        )
        row = cur.fetchone()
        if row:
            return row[0]

    if website:
        cur.execute(
            """
            SELECT p.id
            FROM bank_providers p
            JOIN bank_provider_locations pl ON pl.provider_id=p.id
            WHERE p.website=%s AND pl.location_id=%s
            LIMIT 1
            """,
            (website, location_id),
        )
        row = cur.fetchone()
        if row:
            return row[0]

    cur.execute(
        """
        SELECT p.id
        FROM bank_providers p
        JOIN bank_provider_locations pl ON pl.provider_id=p.id
        WHERE p.normalized_name=%s AND pl.location_id=%s
        LIMIT 1
        """,
        (n_name, location_id),
    )
    row = cur.fetchone()
    return row[0] if row else None


def import_file(
    path: Path,
    *,
    service: str,
    source_name: str,
    source_url: str,
    source_type: str = "discovery",
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = extract_records(payload)
    inserted = 0
    updated = 0
    rejected = 0

    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            source_id = ensure_source(cur, name=source_name, url=source_url, source_type=source_type)
            service_id = ensure_service(cur, service)
            cur.execute(
                "INSERT INTO bank_ingestion_runs(source_id,status,fetched_count) VALUES (%s,'running',%s) RETURNING id",
                (source_id, len(records)),
            )
            run_id = cur.fetchone()[0]

            for index, record in enumerate(records, start=1):
                name = clean(record.get("name"))
                if not name:
                    rejected += 1
                    continue

                location_id = find_or_create_location(cur, record)
                existing_id = find_provider(cur, record, location_id)
                metadata = json.dumps(
                    {
                        "discovered": True,
                        "discovery_source": source_name,
                        "discovery_confidence": record.get("confidence"),
                    },
                    ensure_ascii=False,
                )

                if existing_id:
                    provider_id = existing_id
                    cur.execute(
                        """
                        UPDATE bank_providers SET
                          name=%s,
                          provider_type=COALESCE(NULLIF(%s,''),provider_type),
                          phone=COALESCE(phone,%s),
                          website=COALESCE(website,%s),
                          metadata=COALESCE(metadata,'{}'::jsonb) || %s::jsonb,
                          active=TRUE,
                          updated_at=now()
                        WHERE id=%s
                        """,
                        (
                            name,
                            provider_type(record, service),
                            clean(record.get("phone")),
                            clean(record.get("website")),
                            metadata,
                            provider_id,
                        ),
                    )
                    updated += 1
                else:
                    cur.execute(
                        """
                        INSERT INTO bank_providers(provider_type,name,normalized_name,phone,website,metadata)
                        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                        RETURNING id
                        """,
                        (
                            provider_type(record, service),
                            name,
                            norm(name),
                            clean(record.get("phone")),
                            clean(record.get("website")),
                            metadata,
                        ),
                    )
                    provider_id = cur.fetchone()[0]
                    inserted += 1

                cur.execute(
                    """INSERT INTO bank_provider_locations(provider_id,location_id,is_primary)
                       VALUES (%s,%s,TRUE) ON CONFLICT DO NOTHING""",
                    (provider_id, location_id),
                )
                cur.execute(
                    """
                    INSERT INTO bank_provider_services(provider_id,service_id,confidence,source_id)
                    VALUES (%s,%s,'discovered',%s)
                    ON CONFLICT(provider_id,service_id) DO UPDATE SET
                      source_id=COALESCE(bank_provider_services.source_id,EXCLUDED.source_id),
                      confidence=CASE
                        WHEN bank_provider_services.confidence IN ('official','verified') THEN bank_provider_services.confidence
                        ELSE 'discovered'
                      END
                    """,
                    (provider_id, service_id, source_id),
                )

                raw_blob = json.dumps(record, ensure_ascii=False, sort_keys=True)
                payload_hash = hashlib.sha256(raw_blob.encode("utf-8")).hexdigest()
                source_key = str(record.get("source_id") or record.get("place_id") or f"discovery-{index}")
                cur.execute(
                    """
                    INSERT INTO bank_raw_records(source_id,source_record_key,payload,payload_hash)
                    VALUES (%s,%s,%s::jsonb,%s)
                    ON CONFLICT(source_id,payload_hash) DO NOTHING
                    """,
                    (source_id, source_key, raw_blob, payload_hash),
                )

            cur.execute(
                """
                UPDATE bank_ingestion_runs SET
                  finished_at=now(),status='success',accepted_count=%s,updated_count=%s,rejected_count=%s
                WHERE id=%s
                """,
                (inserted + updated, updated, rejected, run_id),
            )
        conn.commit()

    return {
        "ok": True,
        "fetched": len(records),
        "inserted": inserted,
        "updated": updated,
        "rejected": rejected,
        "service": service,
        "source": source_name,
        "contracts_created": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import raw discovered healthcare providers without creating insurance contracts")
    parser.add_argument("path")
    parser.add_argument("--service", required=True)
    parser.add_argument("--source-name", default="Healthcare Discovery Engine")
    parser.add_argument("--source-url", default="https://www.google.com/maps")
    parser.add_argument("--source-type", default="discovery")
    args = parser.parse_args()
    result = import_file(
        Path(args.path),
        service=args.service,
        source_name=args.source_name,
        source_url=args.source_url,
        source_type=args.source_type,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
