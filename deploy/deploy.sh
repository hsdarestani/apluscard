#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/apluscard}"
cd "$APP_DIR"
git pull --ff-only
docker compose up -d --build
docker compose exec -T web python manage.py migrate --noinput
docker image prune -f
