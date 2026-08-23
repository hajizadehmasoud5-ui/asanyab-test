from fastapi import Query
from fastapi.responses import Response

import app as base

app = base.app


def geography_options(province: str = "", city: str = ""):
    with base.db() as conn:
        insurers = conn.execute(
            "SELECT name FROM bank_insurers WHERE active ORDER BY name"
        ).fetchall()
        services = conn.execute(
            "SELECT DISTINCT name FROM bank_services WHERE name IS NOT NULL AND name<>'' ORDER BY name"
        ).fetchall()

        has_geo = conn.execute("SELECT to_regclass('public.geo_provinces') AS t").fetchone()["t"] is not None
        geo_count = 0
        if has_geo:
            geo_count = conn.execute("SELECT count(*) AS n FROM geo_provinces").fetchone()["n"]

        if geo_count:
            # Canonical catalog + any real provider location not yet present in the catalog.
            provinces = conn.execute(
                """SELECT name FROM (
                       SELECT name FROM geo_provinces
                       UNION
                       SELECT DISTINCT province AS name FROM bank_locations
                       WHERE province IS NOT NULL AND province<>''
                   ) x ORDER BY name"""
            ).fetchall()
            if province:
                cities = conn.execute(
                    """SELECT name FROM (
                           SELECT c.name
                           FROM geo_cities c
                           JOIN geo_provinces p ON p.id=c.province_id
                           WHERE p.name=%s
                           UNION
                           SELECT DISTINCT city AS name FROM bank_locations
                           WHERE province=%s AND city IS NOT NULL AND city<>''
                       ) x ORDER BY name""",
                    (province, province),
                ).fetchall()
            else:
                cities = []
        else:
            provinces = conn.execute(
                """SELECT DISTINCT province AS name FROM bank_locations
                   WHERE province IS NOT NULL AND province<>'' ORDER BY province"""
            ).fetchall()
            if province:
                cities = conn.execute(
                    """SELECT DISTINCT city AS name FROM bank_locations
                       WHERE province=%s AND city IS NOT NULL AND city<>'' ORDER BY city""",
                    (province,),
                ).fetchall()
            else:
                cities = []

        # Neighborhoods stay conservative: only explicit/verified districts from provider addresses.
        if province and city:
            districts = conn.execute(
                """SELECT DISTINCT district FROM bank_locations
                   WHERE province=%s AND city=%s
                     AND district IS NOT NULL AND district<>'' ORDER BY district""",
                (province, city),
            ).fetchall()
        else:
            districts = []

    return {
        "insurers": [x["name"] for x in insurers],
        "services": [x["name"] for x in services],
        "provinces": [x["name"] for x in provinces],
        "cities": [x["name"] for x in cities],
        "districts": [x["district"] for x in districts],
    }


base.geography_options = geography_options


def raw_selection_count(
    insurer: str = "",
    service: str = "",
    province: str = "",
    city: str = "",
    district: str = "",
) -> int:
    """Count the provider bank first; insurer is only an optional relation filter."""
    clauses = ["p.active=TRUE"]
    params = []

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
                FROM bank_contracts c
                JOIN bank_insurers i ON i.id=c.insurer_id
                WHERE c.provider_id=p.id
                  AND c.location_id=l.id
                  AND c.status='active'
                  AND i.name=%s
            )"""
        )
        params.append(insurer)

    sql = f"""
      SELECT count(DISTINCT p.id) AS n
      FROM bank_providers p
      JOIN bank_provider_locations pl ON pl.provider_id=p.id
      JOIN bank_locations l ON l.id=pl.location_id
      {base.SERVICE_JOINS}
      WHERE {' AND '.join(clauses)}
    """
    with base.db() as conn:
        row = conn.execute(sql, params).fetchone()
    return int(row["n"] or 0)


# base.view resolves this global at request time, so the existing UI immediately switches
# from contract-first counting to provider-first counting.
base.selection_count = raw_selection_count


# Replace the legacy contract-first /providers route with a raw-provider-first endpoint.
app.router.routes = [
    route for route in app.router.routes
    if not (getattr(route, "path", None) == "/providers" and "GET" in getattr(route, "methods", set()))
]


@app.get("/providers")
def providers(
    insurer: str = "",
    service: str = "",
    province: str = "",
    city: str = "",
    district: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    clauses = ["p.active=TRUE"]
    params = []

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

    sql = f"""
      SELECT DISTINCT
        p.id,p.name,p.provider_type,p.phone,p.website,
        l.province,l.city,l.district,l.address,l.latitude,l.longitude,
        COALESCE((
          SELECT jsonb_agg(DISTINCT i.name)
          FROM bank_contracts c
          JOIN bank_insurers i ON i.id=c.insurer_id
          WHERE c.provider_id=p.id AND c.location_id=l.id AND c.status='active'
        ), '[]'::jsonb) AS insurers
      FROM bank_providers p
      JOIN bank_provider_locations pl ON pl.provider_id=p.id
      JOIN bank_locations l ON l.id=pl.location_id
      {base.SERVICE_JOINS}
      WHERE {' AND '.join(clauses)}
      ORDER BY p.name,l.city
      LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with base.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"items": rows, "limit": limit, "offset": offset}


@app.middleware("http")
async def provider_first_ui(request, call_next):
    response = await call_next(request)
    if request.url.path.rstrip("/") != "/bank/view" and not request.url.path.endswith("/view"):
        return response
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        return response

    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    text = body.decode("utf-8", errors="replace")

    text = text.replace(
        "خدمت و بیمه را انتخاب کن، بعد استان، شهر و محله را مشخص کن.",
        "خدمت و موقعیت را انتخاب کن؛ بیمه اختیاری است و فقط نتایج را محدود می‌کند.",
    )
    text = text.replace("انتخاب بیمه", "همه بیمه‌ها (اختیاری)")

    # The bank is intentionally incomplete while discovery is expanding; zero is not asserted as reality.
    text = text.replace(
        "<div class='result empty'><strong>۰</strong>",
        "<div class='result empty'><strong>—</strong>",
    )
    text = text.replace(
        "برای این ترکیب هنوز گزینه‌ای ثبت نشده",
        "داده این ترکیب در بانک هنوز کامل نشده",
    )

    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(
        content=text,
        status_code=response.status_code,
        headers=headers,
        media_type="text/html",
    )
