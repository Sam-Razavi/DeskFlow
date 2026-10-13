#!/bin/sh
set -e
alembic upgrade head
if [ "${SEED_DEMO_DATA:-true}" = "true" ]; then
  python -m app.seed
fi
# Railway injects PORT; default to 8000 locally.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
