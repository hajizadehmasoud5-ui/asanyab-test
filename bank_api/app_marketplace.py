"""Read-only patient marketplace API for the isolated DrLinq V1 test deployment."""

from typing import Any

from fastapi import HTTPException, Query

import app as base
import app_geo as current


app = current.app
app.title = "DrLinq Patient Marketplace API"
app.version = "1.0.0-test"


def _provider_filters(
    *,
    insurer: str = "",
    service: str = "",
    province: str = "",
    city: str = "",
    district: str = "",
) -> tuple[list[str], list[Any]]:
    clauses = ["p.active=TRUE"]
    params: list[Any] = []

    if service:
        clauses.append(f"{base.SERVICE_NORM_EXPR}=%s")
        params.append(base.norm(service))
    if province:
        clauses.append("l.province=%s")
        params.append(province)
    if city:
        clauses.append("l.city=%s")
        params.append(city)
    if district:
        clauses.append("l.district=%s")
        params.append(district)
    if insurer:
        clauses.append(
            """EXISTS (
                SELECT 1
                FROM bank_contracts c0
                JOIN bank_insurers i0 ON i0.id=c0.insurer_id
                WHERE c0.provider_id=p.id
                  AND c0.location_id=l.id
                  AND c0.status='active'
                  AND i0.name=%s
            )"""
        )
        params.append(insurer)

    return clauses, params


@app.get("/marketplace/meta")
def marketplace_meta():
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT
              (SELECT count(*) FROM bank_providers WHERE active) AS providers,
              (SELECT count(*) FROM bank_contracts WHERE status='active') AS contracts,
              (SELECT count(DISTINCT insurer_id) FROM bank_contracts WHERE status='active') AS insurers_with_data,
              (SELECT max(last_verified_at) FROM bank_contracts WHERE status='active') AS last_verified_at
            """
        ).fetchone()
    return {
        "counts": row,
        "coverage_complete": False,
        "notice": "پوشش بانک در حال تکمیل است و نبود نتیجه به معنی نبود مرکز در دنیای واقعی نیست.",
    }


@app.get("/marketplace/providers")
def marketplace_providers(
    insurer: str = "",
    service: str = "",
    province: str = "",
    city: str = "",
    district: str = "",
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    clauses, params = _provider_filters(
        insurer=insurer,
        service=service,
        province=province,
        city=city,
        district=district,
    )
    sql = f"""
      WITH candidates AS (
        SELECT DISTINCT
          p.id,
          l.id AS location_id,
          p.name,
          p.provider_type,
          p.medical_license_no,
          COALESCE(NULLIF(p.phone,''), NULLIF(l.phone,'')) AS phone,
          p.website,
          l.province,
          l.city,
          l.district,
          l.address,
          l.latitude,
          l.longitude
        FROM bank_providers p
        JOIN bank_provider_locations pl ON pl.provider_id=p.id
        JOIN bank_locations l ON l.id=pl.location_id
        {base.SERVICE_JOINS}
        WHERE {' AND '.join(clauses)}
      )
      SELECT c.*,
        count(*) OVER() AS total_count,
        COALESCE((
          SELECT jsonb_agg(x.name ORDER BY x.name)
          FROM (
            SELECT DISTINCT i.name
            FROM bank_contracts bc
            JOIN bank_insurers i ON i.id=bc.insurer_id
            WHERE bc.provider_id=c.id
              AND bc.location_id=c.location_id
              AND bc.status='active'
          ) x
        ), '[]'::jsonb) AS insurers,
        COALESCE((
          SELECT jsonb_agg(x.name ORDER BY x.name)
          FROM (
            SELECT DISTINCT s.name
            FROM bank_provider_services ps
            JOIN bank_services s ON s.id=ps.service_id
            WHERE ps.provider_id=c.id
          ) x
        ), '[]'::jsonb) AS services,
        COALESCE((
          SELECT jsonb_agg(x.evidence ORDER BY x.last_verified_at DESC NULLS LAST)
          FROM (
            SELECT DISTINCT jsonb_build_object(
              'name', src.name,
              'url', src.url,
              'source_type', src.source_type,
              'confidence', bc.confidence,
              'last_verified_at', bc.last_verified_at,
              'last_seen_at', bc.last_seen_at
            ) AS evidence,
            bc.last_verified_at
            FROM bank_contracts bc
            JOIN bank_sources src ON src.id=bc.source_id
            WHERE bc.provider_id=c.id
              AND bc.location_id=c.location_id
              AND bc.status='active'
          ) x
        ), '[]'::jsonb) AS sources
      FROM candidates c
      ORDER BY
        CASE WHEN c.phone IS NULL OR c.phone='' THEN 1 ELSE 0 END,
        c.name,
        c.city
      LIMIT %s OFFSET %s
    """
    query_params = [*params, limit, offset]
    with base.db() as conn:
        rows = conn.execute(sql, query_params).fetchall()

    total = int(rows[0]["total_count"]) if rows else 0
    for row in rows:
        row.pop("total_count", None)
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@app.get("/marketplace/providers/{provider_id}")
def marketplace_provider_detail(provider_id: str, location_id: str = ""):
    location_clause = "AND l.id=%s" if location_id else ""
    params: list[Any] = [provider_id]
    if location_id:
        params.append(location_id)

    with base.db() as conn:
        provider = conn.execute(
            """
            SELECT id,name,provider_type,medical_license_no,phone,website,metadata
            FROM bank_providers
            WHERE id=%s AND active=TRUE
            """,
            (provider_id,),
        ).fetchone()
        if not provider:
            raise HTTPException(status_code=404, detail="provider_not_found")

        locations = conn.execute(
            f"""
            SELECT
              l.id AS location_id,
              l.province,
              l.city,
              l.district,
              l.address,
              l.latitude,
              l.longitude,
              COALESCE(NULLIF(p.phone,''), NULLIF(l.phone,'')) AS phone,
              COALESCE((
                SELECT jsonb_agg(x.name ORDER BY x.name)
                FROM (
                  SELECT DISTINCT i.name
                  FROM bank_contracts bc
                  JOIN bank_insurers i ON i.id=bc.insurer_id
                  WHERE bc.provider_id=p.id
                    AND bc.location_id=l.id
                    AND bc.status='active'
                ) x
              ), '[]'::jsonb) AS insurers,
              COALESCE((
                SELECT jsonb_agg(x.evidence ORDER BY x.last_verified_at DESC NULLS LAST)
                FROM (
                  SELECT DISTINCT jsonb_build_object(
                    'name', src.name,
                    'url', src.url,
                    'source_type', src.source_type,
                    'confidence', bc.confidence,
                    'last_verified_at', bc.last_verified_at,
                    'last_seen_at', bc.last_seen_at
                  ) AS evidence,
                  bc.last_verified_at
                  FROM bank_contracts bc
                  JOIN bank_sources src ON src.id=bc.source_id
                  WHERE bc.provider_id=p.id
                    AND bc.location_id=l.id
                    AND bc.status='active'
                ) x
              ), '[]'::jsonb) AS sources
            FROM bank_providers p
            JOIN bank_provider_locations pl ON pl.provider_id=p.id
            JOIN bank_locations l ON l.id=pl.location_id
            WHERE p.id=%s {location_clause}
            ORDER BY pl.is_primary DESC,l.province,l.city
            """,
            params,
        ).fetchall()

        services = conn.execute(
            """
            SELECT DISTINCT s.name
            FROM bank_provider_services ps
            JOIN bank_services s ON s.id=ps.service_id
            WHERE ps.provider_id=%s
            ORDER BY s.name
            """,
            (provider_id,),
        ).fetchall()

    provider["services"] = [row["name"] for row in services]
    provider["locations"] = locations
    return provider
