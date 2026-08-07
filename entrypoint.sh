#!/bin/sh
set -e

if [ "${DJANGO_DEBUG:-0}" != "1" ] && [ -z "${DATABASE_URL:-}" ]; then
  echo "FATAL: DATABASE_URL is required in production. Refusing to fall back to a local SQLite database." >&2
  exit 64
fi

python manage.py migrate --noinput

python manage.py shell -c '
from django.conf import settings
from django.db import connection
if not settings.DEBUG and connection.vendor != "postgresql":
    raise SystemExit(f"FATAL: production database must be PostgreSQL, got {connection.vendor!r}")
print(f"Database OK · vendor={connection.vendor} · name={connection.settings_dict.get(chr(78)+chr(65)+chr(77)+chr(69))}")
'

# Docker Compose supplies a command for background services such as push-worker.
# Honour it instead of accidentally starting another Gunicorn process.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" --timeout 60 --access-logfile - --error-logfile -
