# DrLinq Patient V1 — Handoff

Saved at: 2026-08-28 UTC

## Fully completed

- Audited the existing repository, production root, live provider-bank API, data model, Drive inventory, VPS/container topology, and current n8n endpoint without changing production infrastructure.
- Completed global product-pattern research and saved the V1 product decisions in `DRLINQ_PRODUCT_BLUEPRINT.md`.
- Built a standalone Persian RTL, mobile-first patient experience under `/drlinq-test/` with:
  - plain-language service/need input and Persian normalization;
  - province → city dependency;
  - optional insurance and free/no-insurance search;
  - real provider-bank results with deduplication;
  - provider cards, safe call actions, and provider details;
  - honest loading, API-error, empty-result, verification, and missing-source states;
  - no fake booking slots, ratings, prices, or provider claims.
- Fixed the legacy API field mismatch (`insurers` versus `insurer`) and added a safe fallback from draft `/marketplace/*` endpoints to the current live `/providers` endpoint.
- Stopped claiming an exact total when the legacy API does not return one.
- Rejected malformed concatenated phone values from call CTAs and restored correct HTML `hidden` behavior.
- Added asset versioning (`v=1.0.1`) so GitHub Pages/browser caches receive the verified CSS and JavaScript immediately.
- Completed quick JavaScript syntax checks and core checks for normalization, dental/lab mapping, typo tolerance, deduplication, verification state, and telephone validation.
- Completed live HTTPS E2E checks for dental + Ahvaz + Alborz, laboratory + Ahvaz + Alborz, multiple results, pagination, empty results, provider details, insurer display, source honesty, and site JavaScript errors.
- Confirmed the production root HTML remained byte-for-byte unchanged during the isolated test deployment.

## Partially completed

- `bank_api/app_marketplace.py` contains a richer FastAPI/PostgreSQL marketplace read API with source and freshness support, but it is a draft and is not deployed.
- The live legacy API does not expose source URLs or verification dates. The UI therefore correctly shows “source unavailable / needs review” instead of inventing provenance.
- Responsive CSS is implemented for widths below 900px and 640px, and browser/DOM checks passed. A physical-device mobile run is still required because the available cloud browser did not expose a permitted mobile viewport.
- Data quality still contains city variants and some malformed or concatenated phone values. UI guards are present, but source cleanup is not complete.
- The future patient-request → provider-response marketplace flow is defined in the blueprint but intentionally not implemented in V1.

## Exact files modified or added

- `.github/workflows/deploy-drlinq-marketplace-test.yml`
- `DRLINQ_PRODUCT_BLUEPRINT.md`
- `DRLINQ_HANDOFF.md`
- `bank_api/Containerfile.marketplace-test`
- `bank_api/app.py`
- `bank_api/app_marketplace.py`
- `drlinq-test/Containerfile`
- `drlinq-test/about-data.html`
- `drlinq-test/assets/api.js`
- `drlinq-test/assets/config.js`
- `drlinq-test/assets/core.js`
- `drlinq-test/assets/home.js`
- `drlinq-test/assets/provider.js`
- `drlinq-test/assets/results.js`
- `drlinq-test/assets/styles.css`
- `drlinq-test/health.json`
- `drlinq-test/index.html`
- `drlinq-test/nginx.conf`
- `drlinq-test/package.json`
- `drlinq-test/provider.html`
- `drlinq-test/results.html`
- `drlinq-test/tests/core.test.mjs`

## Current architecture

1. Production web root: GitHub Pages at `https://drlinq.ir/` (unchanged).
2. Safe test UI: static GitHub Pages subpath at `https://drlinq.ir/drlinq-test/`.
3. Runtime configuration: `drlinq-test/assets/config.js` points to the existing read API at `https://n8n.drlinq.ir/bank`.
4. Client API adapter: tries `/marketplace/providers` and `/marketplace/providers/:id`, then safely falls back to `/providers` when the richer endpoints return 404.
5. Client matching core: Persian normalization, everyday-language service aliases, small typo tolerance, deterministic deduplication, source-state labels, safe URLs/phones.
6. Provider details: use the selected result in `sessionStorage`; otherwise query the API fallback using the search context.
7. Current live provider bank: PostgreSQL-backed API exposed behind the existing VPS/n8n domain.
8. Draft only: `bank_api/app_marketplace.py` and container files are preserved on this WIP branch but are not connected to the live route.

## What remains

- Review and harden the draft marketplace API against the live schema using a read-only, isolated configuration.
- Replace the preserved deployment workflow with a safe design before it is ever enabled.
- Expose source URL/type and last-verified dates from the API, then re-run provider-detail trust tests.
- Run the final 390px/physical-device mobile E2E pass.
- Clean city aliases and malformed source phone values in the data pipeline.
- Only after those checks, decide whether to promote the test UI to the production root.

## Exact next step to continue

Disable/remove the unsafe VPS deployment workflow, then review `bank_api/app_marketplace.py` against the live PostgreSQL schema and produce a read-only isolated test-deployment plan that does not copy production credentials or modify the shared Caddy configuration.

## Known errors and blockers

- The current live API has no `/marketplace/*` routes; the frontend uses the tested legacy fallback.
- Source/freshness evidence is absent from the legacy response, so richer verification cannot be completed without the draft API or an API change.
- Observed live API/page responses can take several seconds; no performance remediation has been made.
- Some upstream data contains noncanonical city labels and malformed phone strings.
- `.github/workflows/deploy-drlinq-marketplace-test.yml` is preserved only as WIP. It must **not** be enabled or manually dispatched: it copies production DB environment values and edits the shared VPS Caddy configuration. Its push trigger targets only `drlinq-patient-marketplace-v1`, not this handoff branch, so pushing `drlinq-patient-v1-wip` does not deploy it.
- A physical mobile-device/browser viewport was not available in the permitted test environment.

## Deployment status

- Safe static test is already live: `https://drlinq.ir/drlinq-test/`.
- Test health endpoint reports version `1.0.1`.
- Existing API health endpoint is live at `https://n8n.drlinq.ir/bank/health`.
- GitHub Pages and site-health workflows passed for the safe static deployment.
- Production root remains unchanged.
- The richer backend/container draft and the WIP branch are not deployed.
