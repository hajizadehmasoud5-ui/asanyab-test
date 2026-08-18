# AlanOffer / Cloudiva deploy branch

This branch is the runtime source for the existing Python service.

## Keep outside Git
Runtime data and secrets must stay outside version control:
- `/app/data/`
- `AVALAI_API_KEY`
- `LIPSYNC_API_TOKEN`
- `ALANOFFER_ADMIN_TOKEN`
- `ALANOFFER_ADMIN_SETUP_SECRET`
- any `.env` file

## Runtime files
- `myapp.py` — existing Content Studio + video service
- `alanoffer_blueprint.py` — AlanOffer API/admin/MVP backend
- `requirements.txt`
- `start.sh`
- `cleanup_server.sh`

## Important migration rule
Never run a blind `rm -rf $(ls -A)` on `/app`. Preserve `/app/data` before any Git migration. The cleanup script only removes known old backups/installers and Python caches.
