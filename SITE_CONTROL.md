# DrLinq Site Control

## Goal
Use this GitHub repository as the main control plane for DrLinq so routine changes can be made from ChatGPT through the connected GitHub account, with as few manual dashboard steps as possible.

## Live site
- Domain: https://drlinq.ir/
- Hosting: GitHub Pages
- Repository: `hajizadehmasoud5-ui/asanyab-test`
- Branch: `main`
- Homepage: `index.html`

## Search / SEO
- Search Console ownership: verified
- Homepage indexing request: submitted
- Sitemap: `https://drlinq.ir/sitemap.xml`
- Robots: `https://drlinq.ir/robots.txt`
- Canonical homepage: `https://drlinq.ir/`

## Backend
- Public API base currently used by `index.html`: `https://python-0jatcc.cldv.dev/alanoffer`
- Source file in this repository: `backend/alanoffer_blueprint.py`
- Backend source changes in GitHub do NOT automatically prove that the live Cloudiva service has updated; deployment/restart must be verified separately.
- Admin endpoints require `X-Admin-Token`; never commit the real admin token to GitHub.

## Automated health checks
Workflow: `.github/workflows/site-health.yml`

It checks on every push to `main`, manually, and every 6 hours:
- homepage is reachable
- canonical and meta description are present
- `robots.txt` is reachable and points to the sitemap
- `sitemap.xml` is reachable and contains the public homepage
- live backend health endpoint responds with `ok: true`

## Public MVP flow
Patient request -> service -> province-capital city -> up to two priorities -> approximate case size -> wait time -> mobile/WhatsApp -> request ID.

## What can be controlled from ChatGPT now
- GitHub Pages frontend code and copy
- public page structure and styling
- SEO metadata
- `robots.txt` and `sitemap.xml`
- backend source code stored in GitHub
- GitHub Actions health checks
- Android/source files in this repository
- rollback by restoring earlier GitHub content when needed

## What still needs an external control bridge
- Cloudiva live backend deployment/restart
- Cloudflare DNS/account-level settings
- Google Search Console dashboard actions
- secrets/tokens stored outside GitHub

The preferred next infrastructure step is a one-time connection from the Cloudiva backend service to this GitHub repository with auto-deploy on `main`, if Cloudiva supports it. Until that is confirmed, do not assume a backend commit is live.

## Privacy boundary
Do not copy patient contact details or treatment-request records into GitHub. GitHub is for source/configuration, not sensitive patient data.

## Control rule
Before risky production changes, read the current file and preserve a rollback point. Do not change DNS, secrets, domain ownership, or deployment configuration by assumption.

## Current SEO hygiene
The sitemap contains only the public homepage. Prototype/admin pages are excluded from crawler discovery through `robots.txt` where appropriate.
