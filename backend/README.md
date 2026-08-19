# DrLinq backend — active MVP

Active backend file: `alanoffer_blueprint.py`.

The route prefix stays `/alanoffer` temporarily so the existing Cloudiva integration does not break while the public product is DrLinq.

## What the MVP does

Public patient flow:
- treatment/service
- province-capital city
- top priorities (price, quality, speed, installments, distance)
- approximate case size
- how long the patient can wait
- mobile/WhatsApp

After completion, the request is stored with status `needs_provider_search` and receives a request ID.

Demand-first operator flow:
- list real requests
- copy a ready provider-outreach message
- find providers only for an existing request
- add provider WhatsApp/Instagram to the growing provider bank
- record contacted/interested/rejected/no-reply/selected
- update request status

This makes the provider bank grow from actual demand instead of trying to pre-build the whole country.

## Public endpoints

- `GET /alanoffer/api/chat/health`
- `POST /alanoffer/api/chat/start`
- `POST /alanoffer/api/chat/message`
- `GET /alanoffer/api/request/<request_id>`

## Operator endpoints

Require header `X-Admin-Token` matching `DRLINQ_ADMIN_TOKEN`.

- `GET /alanoffer/api/admin/requests`
- `POST /alanoffer/api/admin/requests/<request_id>/status`
- `POST /alanoffer/api/admin/requests/<request_id>/providers`
- `POST /alanoffer/api/admin/requests/<request_id>/providers/<provider_id>/status`

Operator UI: `/admin.html` on the static site.

## Integration on Cloudiva

```python
from alanoffer_blueprint import create_alanoffer_blueprint
app.register_blueprint(create_alanoffer_blueprint(DATA_ROOT))
```

Replace the old `alanoffer_blueprint.py` in the existing Flask service with the GitHub version, configure environment variables, and restart the service.

Required environment variables:

```text
ALANOFFER_DB_PATH=
ALANOFFER_CORS_ORIGINS=https://hajizadehmasoud5-ui.github.io,https://drlinq.ir,https://www.drlinq.ir
DRLINQ_ADMIN_TOKEN=<long-random-secret>
```

## Storage

SQLite tables:
- `chat_sessions`
- `chat_records`
- `providers`
- `request_providers`

Current backend version: `0.4.0`.
