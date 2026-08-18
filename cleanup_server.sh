#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/app}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="/tmp/alanoffer_cleanup_${STAMP}.tar.gz"

if [ ! -d "$APP_DIR" ]; then
  echo "APP_DIR not found: $APP_DIR" >&2
  exit 1
fi

cd "$APP_DIR"

# Safety gate: never run outside the intended app directory.
if [ "$(pwd)" != "/app" ] && [ "${ALLOW_NON_APP:-0}" != "1" ]; then
  echo "Refusing to clean outside /app" >&2
  exit 1
fi

# Back up only files we may delete. Runtime data/ and active source are untouched.
mapfile -t OLD_FILES < <(find . -maxdepth 1 -type f \( \
  -name 'myapp_backup*.py' -o \
  -name 'myapp_before_*.py' -o \
  -name 'myapp_old*.py' -o \
  -name 'myapp_v*_backup.py' -o \
  -name 'requirements_before_*.txt' -o \
  -name 'install_content_studio_*.py' \
\) -printf '%f\n' | sort)

if [ "${#OLD_FILES[@]}" -gt 0 ]; then
  tar -czf "$BACKUP" "${OLD_FILES[@]}"
  rm -f -- "${OLD_FILES[@]}"
  echo "Backup: $BACKUP"
  echo "Removed ${#OLD_FILES[@]} old files."
else
  echo "No known old backup/installer files found."
fi

# Python caches are always disposable.
find . -maxdepth 2 -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true

printf '\nCurrent /app root:\n'
find . -maxdepth 1 -mindepth 1 -printf '%f\n' | sort
