#!/bin/sh
# Start the API: apply database migrations, then run uvicorn.
# RUN_MIGRATIONS=false skips the migrations (e.g. when a separate release step runs them,
# or on every instance but one when several start at the same time).
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "Running database migrations"
  alembic upgrade head
fi

# --proxy-headers + FORWARDED_ALLOW_IPS: trust X-Forwarded-For only from the proxy in
# front (its IP), so rate limits see the real client IP. "*" only if the API is not
# reachable except through that proxy.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
  --no-server-header
