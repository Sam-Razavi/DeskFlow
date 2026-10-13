#!/bin/sh
# One image, two roles, chosen by SERVICE_ROLE (default: api). A platform that cannot set a custom
# start command per service, or whose config files are not honoured, only needs this variable.
set -e

case "${SERVICE_ROLE:-api}" in
  worker)
    # The background worker never touches the schema: the api service migrates it on deploy.
    exec arq app.worker.WorkerSettings
    ;;
  api) ;;
  *)
    echo "Unknown SERVICE_ROLE '${SERVICE_ROLE}': expected 'api' or 'worker'." >&2
    exit 1
    ;;
esac

alembic upgrade head

# Demo accounts have publicly documented passwords. They are on by default for local development
# and off by default in production, where they must be requested explicitly.
seed="${SEED_DEMO_DATA:-}"
if [ -z "$seed" ]; then
  if [ "${ENVIRONMENT:-development}" = "production" ]; then seed=false; else seed=true; fi
fi
if [ "$seed" = "true" ]; then
  python -m app.seed
fi

# The first administrator, for deployments that start with no users. Safe on every deploy: an
# existing account is never changed.
if [ -n "${ADMIN_EMAIL:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
  python -m app.create_admin
fi

# PORT is set by the platform. HOST is 0.0.0.0 (IPv4) by default; use "::" where the private
# network is IPv6-only (Railway environments created before October 2025).
exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips='*'
