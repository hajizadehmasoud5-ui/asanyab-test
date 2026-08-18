# AlanOffer backend — active MVP

Active backend file: `alanoffer_blueprint.py`

This is a Flask Blueprint intended for the existing Cloudiva Python service and mounts under `/alanoffer`.

## Required endpoints

- `GET /alanoffer/api/chat/health`
- `POST /alanoffer/api/chat/start`
- `POST /alanoffer/api/chat/message`

## Integration

In the existing Flask service, import and register the blueprint once:

```python
from alanoffer_blueprint import create_alanoffer_blueprint

app.register_blueprint(create_alanoffer_blueprint(DATA_ROOT))
```

If the service already imports `create_alanoffer_blueprint`, replace the old `alanoffer_blueprint.py` with the new file and restart the service. No Node server is required.

## Storage

SQLite is stored under `<DATA_ROOT>/alanoffer/alanoffer.db` unless `ALANOFFER_DB_PATH` is set.

Tables used by this MVP:

- `chat_sessions`: temporary conversation state
- `chat_records`: completed buyer/seller records

## Current scope

The Chat-first MVP is national (`scope=iran`). It currently uses a deterministic structured conversation (`ai=false`) so the buyer/seller loop can be tested reliably before adding an LLM, Match, and notifications.
