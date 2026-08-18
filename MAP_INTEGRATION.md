# AlanOffer — Map & Place Data Plan

## Decision
Primary Iran map/place provider: **Neshan Maps Platform**.

Why:
- Web/mobile map SDKs for Iran
- Search API for POIs/businesses
- Search results include title, address, neighbourhood, region, type and coordinates
- Routing/deep links available
- Pay-as-you-go pricing and test credit

Waze is navigation-only for our use case and is not the source of the AlanOffer business directory.
Google Places can be used only as a secondary live lookup/enrichment source because its content storage and attribution rules are stricter.

## Current test implementation
- Main directory: interactive Ahvaz map for businesses that have coordinates.
- Add-business page: map pin picker + structured categories + local test storage.
- Test base map: OpenStreetMap/Leaflet.
- Navigation button: Neshan deep link when latitude/longitude exist.

## Production architecture
Do NOT put the Neshan Search API key in public GitHub Pages JavaScript.

Browser/App -> AlanOffer backend endpoint -> Neshan Search API

Example private backend request:
`GET https://api.neshan.org/v3/search?q=<encoded-json>`
Header:
`Api-Key: <SERVER_SECRET>`

Ahvaz default center:
- latitude: 31.3183
- longitude: 48.6706

## Search/seeding strategy for Ahvaz
Use the API live for verification/search. Build AlanOffer's persistent directory from merchant submissions, admin verification, permitted/importable datasets, and user corrections. Do not blindly bulk-copy third-party place databases without checking their data-use terms.

Priority search terms:
- دندانپزشکی / دندانپزشک / کلینیک دندانپزشکی
- پزشک / درمانگاه / کلینیک / بیمارستان
- داروخانه / آزمایشگاه / رادیولوژی / فیزیوتراپی
- رستوران / فست فود / کافه
- میوه فروشی / نانوایی / شیرینی فروشی / پروتئینی / لبنیات
- آرایشگاه / تعمیرگاه / پنچرگیری / کارواش
- سوپرمارکت / پوشاک / موبایل / املاک / بیمه

## Next infrastructure step
Add a tiny backend/serverless proxy and store businesses in a shared database. At that point records added by one user become visible to all users instead of only the same device.