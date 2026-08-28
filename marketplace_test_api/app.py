from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path

import psycopg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

from marketplace import install_marketplace


APP_NAME = os.environ.get("APP_NAME", "DrLinq Marketplace Test")
BRAND_NAME = os.environ.get("BRAND_NAME", "دکترلینک")
DOMAIN = os.environ.get("DOMAIN", "drlinq.ir")

app = FastAPI(title=APP_NAME, version="0.9.0-test")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"https://{DOMAIN}", f"https://www.{DOMAIN}"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def dsn() -> str:
    return " ".join(
        [
            f"host={os.environ.get('DB_HOST', 'marketplace-test-postgres')}",
            f"port={os.environ.get('DB_PORT', '5432')}",
            f"dbname={os.environ['DB_NAME']}",
            f"user={os.environ['DB_USER']}",
            f"password={os.environ['DB_PASSWORD']}",
        ]
    )


def norm(value: str) -> str:
    value = (value or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    return re.sub(r"\s+", " ", value).strip().lower()


@contextmanager
def db():
    with psycopg.connect(dsn(), row_factory=dict_row) as connection:
        yield connection


@app.on_event("startup")
def startup() -> None:
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with db() as connection:
        connection.execute(schema)
        connection.commit()


@app.get("/health")
def health():
    with db() as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM bank_providers WHERE active=TRUE) AS providers,
              (SELECT count(*) FROM bank_services) AS services,
              (SELECT count(*) FROM marketplace_requests) AS test_requests
            """
        ).fetchone()
    return {
        "ok": True,
        "environment": "isolated-test",
        "production_writes": False,
        "app_name": APP_NAME,
        "brand_name": BRAND_NAME,
        "domain": DOMAIN,
        "counts": counts,
    }


@app.get("/filters")
def filters(province: str = "", city: str = ""):
    with db() as connection:
        insurers = connection.execute(
            "SELECT name FROM bank_insurers WHERE active ORDER BY name"
        ).fetchall()
        services = connection.execute(
            "SELECT DISTINCT name FROM bank_services WHERE name<>'' ORDER BY name"
        ).fetchall()
        provinces = connection.execute(
            """
            SELECT DISTINCT province AS name FROM bank_locations
            WHERE province IS NOT NULL AND province<>'' ORDER BY province
            """
        ).fetchall()
        cities = (
            connection.execute(
                """
                SELECT DISTINCT city AS name FROM bank_locations
                WHERE province=%s AND city IS NOT NULL AND city<>'' ORDER BY city
                """,
                (province,),
            ).fetchall()
            if province
            else []
        )
        districts = (
            connection.execute(
                """
                SELECT DISTINCT district AS name FROM bank_locations
                WHERE province=%s AND city=%s
                  AND district IS NOT NULL AND district<>'' ORDER BY district
                """,
                (province, city),
            ).fetchall()
            if province and city
            else []
        )
    return {
        "insurers": [row["name"] for row in insurers],
        "services": [row["name"] for row in services],
        "provinces": [row["name"] for row in provinces],
        "cities": [row["name"] for row in cities],
        "districts": [row["name"] for row in districts],
    }


install_marketplace(app, db, norm, BRAND_NAME, DOMAIN)
