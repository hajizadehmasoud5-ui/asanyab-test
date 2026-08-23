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


@app.middleware("http")
async def conservative_empty_results(request, call_next):
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
