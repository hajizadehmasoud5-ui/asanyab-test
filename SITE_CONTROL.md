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
- Live Cloudiva service: `python-0jatcc`
- Backend source in `main`: `backend/alanoffer_blueprint.py`
- Dedicated deploy branch: `cloudiva-deploy`
- Deploy-branch runtime files: `server.py`, `alanoffer_blueprint.py`, `requirements.txt`, `start.sh`
- Admin endpoints require `X-Admin-Token`; never commit the real admin token to GitHub.
- Production runtime data root: `/data`
- SQLite database path by default: `/data/alanoffer/alanoffer.db`

## Cloudiva control bridge
Workflow: `.github/workflows/chabokan-control.yml`
Control request: `chabokan-control.json`
Sanitized result: `cloudiva-control-result.json`

The bridge uses the official Cloudiva CLI (`@cloudiva.net/cli`, command `diva`) and a GitHub Actions secret. The secret value is never committed to the repository.

Verified working:
- Cloudiva API-token login
- access to service `python-0jatcc`
- safe status check
- start / restart control
- guarded deploy from `cloudiva-deploy`
- live backend health verification
- backend version `0.4.0`
- persistent `/data` storage survives a real service restart

Allowed control actions:
- `status`
- `restart`
- `start`
- `deploy`

Sensitive command output is suppressed because this repository is public. Service logs must not be printed into public GitHub Actions logs.

## Persistent data verification
Cloudiva persistent path `/data` is enabled for `python-0jatcc`.
The deploy runtime now defaults `DATA_ROOT` to `/data`, so DrLinq runtime data is stored under `/data/alanoffer/`.
A synthetic request was created, the service was restarted, and the same request remained available afterwards. The sanitized verification is stored in `cloudiva-persistence-result.json`.

Because persistence has been verified, guarded backend deploys from the `cloudiva-deploy` branch are now enabled.

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
- Cloudiva service status/start/restart/deploy through the secured bridge
- Android/source files in this repository
- rollback by restoring earlier GitHub content when needed

## Remaining external/control gaps
- Cloudflare DNS/account-level settings
- Google Search Console dashboard actions
- secrets/tokens remain stored only in protected secret stores

## Privacy boundary
Do not copy patient contact details, treatment-request records, service logs, or other sensitive runtime data into this public GitHub repository. GitHub is for source/configuration and sanitized status only.

## Control rule
Before risky production changes, read the current file and preserve a rollback point. Do not change DNS, secrets, domain ownership, deployment configuration, or runtime data by assumption.

## Current SEO hygiene
The sitemap contains only the public homepage. Prototype/admin pages are excluded from crawler discovery through `robots.txt` where appropriate.
