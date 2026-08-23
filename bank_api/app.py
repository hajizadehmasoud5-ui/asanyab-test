import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="DrLinq Provider Bank", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://drlinq.ir", "https://www.drlinq.ir"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def dsn() -> str:
    host = os.environ.get("DB_HOST", "postgres")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ["DB_NAME"]
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    return f"host={host} port={port} dbname={name} user={user} password={password}"


@contextmanager
def db():
    with psycopg.connect(dsn(), row_factory=dict_row) as conn:
        yield conn


@app.on_event("startup")
def startup() -> None:
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with db() as conn:
        conn.execute(schema)
        conn.commit()


@app.get("/health")
def health():
    with db() as conn:
        value = conn.execute("SELECT 1 AS ok").fetchone()
    return {"ok": bool(value and value["ok"] == 1), "service": "drlinq-bank-api"}


@app.get("/stats")
def stats():
    with db() as conn:
        counts = conn.execute(
            """
            SELECT
              (SELECT count(*) FROM bank_providers WHERE active) AS providers,
              (SELECT count(*) FROM bank_locations) AS locations,
              (SELECT count(*) FROM bank_contracts WHERE status='active') AS contracts,
              (SELECT count(*) FROM bank_insurers WHERE active) AS insurers,
              (SELECT count(*) FROM bank_sources WHERE active) AS sources
            """
        ).fetchone()
        latest = conn.execute(
            "SELECT finished_at, status, fetched_count, accepted_count, rejected_count FROM bank_ingestion_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    return {"counts": counts, "latest_ingestion": latest}


@app.get("/filters")
def filters():
    with db() as conn:
        insurers = conn.execute("SELECT name FROM bank_insurers WHERE active ORDER BY name").fetchall()
        provinces = conn.execute("SELECT DISTINCT province FROM bank_locations WHERE province IS NOT NULL AND province<>'' ORDER BY province").fetchall()
        cities = conn.execute("SELECT DISTINCT city FROM bank_locations WHERE city IS NOT NULL AND city<>'' ORDER BY city LIMIT 500").fetchall()
        services = conn.execute("SELECT name FROM bank_services ORDER BY name LIMIT 500").fetchall()
    return {
        "insurers": [x["name"] for x in insurers],
        "provinces": [x["province"] for x in provinces],
        "cities": [x["city"] for x in cities],
        "services": [x["name"] for x in services],
    }


@app.get("/providers")
def providers(
    q: str = "",
    insurer: str = "",
    service: str = "",
    province: str = "",
    city: str = "",
    district: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    clauses = ["p.active = TRUE", "c.status = 'active'"]
    params: list[object] = []
    if q:
        clauses.append("(p.name ILIKE %s OR l.address ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    if insurer:
        clauses.append("i.name = %s")
        params.append(insurer)
    if service:
        clauses.append("s.name = %s")
        params.append(service)
    if province:
        clauses.append("l.province = %s")
        params.append(province)
    if city:
        clauses.append("l.city = %s")
        params.append(city)
    if district:
        clauses.append("l.district = %s")
        params.append(district)

    sql = f"""
      SELECT DISTINCT
        p.id, p.name, p.provider_type, p.phone, p.website,
        l.province, l.city, l.district, l.address, l.latitude, l.longitude,
        i.name AS insurer,
        c.confidence, c.last_verified_at,
        src.url AS source_url
      FROM bank_providers p
      JOIN bank_provider_locations pl ON pl.provider_id=p.id
      JOIN bank_locations l ON l.id=pl.location_id
      JOIN bank_contracts c ON c.provider_id=p.id AND c.location_id=l.id
      JOIN bank_insurers i ON i.id=c.insurer_id
      JOIN bank_sources src ON src.id=c.source_id
      LEFT JOIN bank_provider_services ps ON ps.provider_id=p.id
      LEFT JOIN bank_services s ON s.id=ps.service_id
      WHERE {' AND '.join(clauses)}
      ORDER BY p.name, l.city
      LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"items": rows, "limit": limit, "offset": offset}
