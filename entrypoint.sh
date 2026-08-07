#!/bin/sh
set -e

if [ "${DJANGO_DEBUG:-0}" != "1" ] && [ -z "${DATABASE_URL:-}" ]; then
  echo "FATAL: DATABASE_URL is required in production. Refusing to fall back to a local SQLite database." >&2
  exit 64
fi

python manage.py migrate --noinput

if [ "${DJANGO_DEBUG:-0}" = "1" ]; then
  python manage.py check_database_integrity --allow-non-postgres
else
  python manage.py check_database_integrity
fi

# Docker Compose supplies a command for background services such as push-worker.
# Honour it instead of accidentally starting another Gunicorn process.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" --timeout 60 --access-logfile - --error-logfile -
