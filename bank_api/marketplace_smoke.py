from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request

import psycopg
from psycopg.rows import dict_row


def dsn() -> str:
    return " ".join(
        [
            f"host={os.environ.get('DB_HOST', 'postgres')}",
            f"port={os.environ.get('DB_PORT', '5432')}",
            f"dbname={os.environ['DB_NAME']}",
            f"user={os.environ['DB_USER']}",
            f"password={os.environ['DB_PASSWORD']}",
        ]
    )


def call(base_url: str, method: str, path: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path}: HTTP {exc.code}: {detail}") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    with psycopg.connect(dsn(), row_factory=dict_row) as conn:
        conn.execute("DELETE FROM marketplace_requests WHERE is_test=TRUE")
        sample = conn.execute(
            """
            SELECT p.id AS provider_id,p.name,l.province,l.city,s.name AS service
            FROM bank_providers p
            JOIN bank_provider_locations pl ON pl.provider_id=p.id
            JOIN bank_locations l ON l.id=pl.location_id
            JOIN bank_provider_services ps ON ps.provider_id=p.id
            JOIN bank_services s ON s.id=ps.service_id
            WHERE p.active=TRUE AND l.province<>'' AND l.city<>'' AND s.name<>''
            ORDER BY p.name,l.city,s.name
            LIMIT 1
            """
        ).fetchone()
        conn.commit()
    if not sample:
        raise RuntimeError("No provider with service and location exists in the current bank")

    created = call(
        args.base_url,
        "POST",
        "/marketplace/requests",
        {
            "province": sample["province"],
            "city": sample["city"],
            "service": sample["service"],
            "preferred_time": "اولین زمان ممکن",
            "budget_min": 10000000,
            "budget_max": 20000000,
            "contact": "09120000000",
            "is_test": True,
        },
    )
    matches = created.get("matches", [])
    target = next((m for m in matches if m["provider_id"] == str(sample["provider_id"])), None)
    if not target:
        raise RuntimeError("Sample provider was not returned by matching")

    submitted = call(
        args.base_url,
        "POST",
        f"/marketplace/requests/{created['request_id']}/submit",
        {"public_token": created["public_token"], "provider_ids": [target["provider_id"]]},
    )

    with psycopg.connect(dsn(), row_factory=dict_row) as conn:
        access = conn.execute(
            "SELECT access_token FROM marketplace_provider_access WHERE provider_id=%s",
            (sample["provider_id"],),
        ).fetchone()
    dashboard = call(
        args.base_url,
        "GET",
        f"/marketplace/provider/dashboard?access_token={access['access_token']}",
    )
    provider_request = next(
        item for item in dashboard["requests"] if item["request_id"] == created["request_id"]
    )
    response = call(
        args.base_url,
        "POST",
        "/marketplace/provider/respond",
        {
            "access_token": access["access_token"],
            "match_id": provider_request["match_id"],
            "decision": "interested",
            "estimated_price_min": 12000000,
            "estimated_price_max": 18000000,
            "earliest_available": "فردا ساعت ۱۷",
            "note": "پاسخ آزمایشی خودکار بازارچه",
        },
    )
    patient = call(
        args.base_url,
        "GET",
        f"/marketplace/requests/{created['request_id']}?token={created['public_token']}",
    )
    if patient["request"]["status"] != "provider_interested" or not patient["offers"]:
        raise RuntimeError("Provider response was not visible to the patient")
    selected = call(
        args.base_url,
        "POST",
        f"/marketplace/requests/{created['request_id']}/select",
        {"public_token": created["public_token"], "match_id": provider_request["match_id"]},
    )
    final_state = call(
        args.base_url,
        "GET",
        f"/marketplace/requests/{created['request_id']}?token={created['public_token']}",
    )
    if final_state["request"]["status"] != "selected":
        raise RuntimeError("Patient selection did not reach selected status")

    print(
        json.dumps(
            {
                "ok": True,
                "request_id": created["request_id"],
                "matched": len(matches),
                "notified": submitted["notified"],
                "provider_response": response["status"],
                "final_status": selected["status"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
