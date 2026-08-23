from __future__ import annotations

import json
from datetime import datetime, timezone

from app_geo import raw_selection_count

SERVICES = [
    "داروخانه",
    "دندانپزشکی",
    "آزمایشگاه",
    "فیزیوتراپی",
    "رادیولوژی",
    "بیمارستان",
    "درمانگاه",
]

CITIES = [
    ("تهران", "تهران"),
    ("خوزستان", "اهواز"),
]


def main() -> None:
    coverage: dict[str, dict[str, dict[str, int | str]]] = {}
    for province, city in CITIES:
        key = f"{province}/{city}"
        coverage[key] = {}
        for service in SERVICES:
            try:
                coverage[key][service] = {
                    "count": raw_selection_count(service=service, province=province, city=city)
                }
            except Exception as exc:
                coverage[key][service] = {"error": str(exc)}
    print(
        json.dumps(
            {
                "coverage": coverage,
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
