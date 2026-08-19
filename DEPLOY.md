# DrLinq / Cloudiva deploy branch

This branch is now dedicated to the DrLinq demand-first backend only.

Runtime files:
- `server.py` — minimal Flask entrypoint
- `alanoffer_blueprint.py` — DrLinq API/admin backend v0.4.0
- `requirements.txt` — Flask only
- `start.sh` — service start command

Keep runtime data and secrets outside Git:
- `/app/data/`
- `DRLINQ_ADMIN_TOKEN`
- `ALANOFFER_DB_PATH`

Old Asanyab/AlanOffer chat and video-studio runtime files were removed from this branch.
