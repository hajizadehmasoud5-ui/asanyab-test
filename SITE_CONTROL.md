# DrLinq Site Control

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

## Public MVP flow
Patient request -> service -> province-capital city -> up to two priorities -> approximate case size -> wait time -> mobile/WhatsApp -> request ID.

## Control rule
Static site files on GitHub Pages can be edited from the connected GitHub workflow. Before risky changes, read the current file and preserve a rollback point. Do not change DNS, domain, backend secrets, or deployment configuration by assumption.

## Current SEO hygiene
The sitemap contains only the public homepage. Prototype/admin pages are excluded from crawler discovery through `robots.txt` where appropriate.
