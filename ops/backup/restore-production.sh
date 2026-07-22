#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/root/apluscard}"
BACKUP_ENV="${BACKUP_ENV:-$APP_DIR/.backup.env}"
SNAPSHOT_ID="${1:-latest}"
RESTORE_DIR=""

usage() {
  cat <<'TEXT'
Vollständige Production-Wiederherstellung aus einem verschlüsselten Restic-Snapshot.

ACHTUNG: Die aktuelle Datenbank und der aktuelle Media-Inhalt werden ersetzt.

Ausführung:
  RESTORE_PRODUCTION=YES ./ops/backup/restore-production.sh [snapshot-id|latest]
TEXT
}

[[ "${RESTORE_PRODUCTION:-}" == "YES" ]] || { usage; exit 2; }
[[ -f "$BACKUP_ENV" ]] || { echo "Backup-Konfiguration fehlt: $BACKUP_ENV" >&2; exit 1; }
# shellcheck disable=SC1090
set -a
source "$BACKUP_ENV"
set +a

required=(RESTIC_REPOSITORY RESTIC_PASSWORD AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY)
for variable in "${required[@]}"; do
  [[ -n "${!variable:-}" ]] || { echo "$variable fehlt in $BACKUP_ENV" >&2; exit 1; }
done

for command in docker restic sha256sum; do
  command -v "$command" >/dev/null 2>&1 || { echo "$command ist nicht installiert." >&2; exit 1; }
done

mkdir -p "$APP_DIR" /var/lib/apluscard-backup
cd "$APP_DIR"
[[ -f docker-compose.yml ]] || { echo "Repository muss zuerst nach $APP_DIR geklont werden." >&2; exit 1; }

RESTORE_DIR="$(mktemp -d /var/lib/apluscard-backup/production-restore.XXXXXX)"
chmod 700 "$RESTORE_DIR"
trap '[[ -n "$RESTORE_DIR" && -d "$RESTORE_DIR" ]] && rm -rf "$RESTORE_DIR"' EXIT

HOST_TAG="${BACKUP_HOST_TAG:-apluscard-production}"
restic restore "$SNAPSHOT_ID" --host "$HOST_TAG" --tag apluscard --target "$RESTORE_DIR"
BACKUP_DIR="$(find "$RESTORE_DIR" -type f -name database.dump -printf '%h\n' | head -n 1)"
[[ -n "$BACKUP_DIR" ]] || { echo "database.dump fehlt im Snapshot." >&2; exit 1; }

(
  cd "$BACKUP_DIR"
  sha256sum -c SHA256SUMS
  tar -tzf media.tar.gz >/dev/null
  test -s production.env
)

if [[ -f .env ]]; then
  install -m 600 .env ".env.before-restore.$(date -u +%Y%m%dT%H%M%SZ)"
fi
install -m 600 "$BACKUP_DIR/production.env" .env

# Build the exact Git version currently checked out, then bring up PostgreSQL only.
docker compose build web
docker compose up -d db

ready=0
for _ in $(seq 1 60); do
  if docker compose exec -T db sh -lc 'pg_isready --username="$POSTGRES_USER" --dbname=postgres' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
[[ "$ready" -eq 1 ]] || { echo "PostgreSQL wurde nicht rechtzeitig bereit." >&2; exit 1; }

docker compose stop web >/dev/null 2>&1 || true

# PostgreSQL 16 dropdb --force terminates remaining application connections safely.
docker compose exec -T db sh -lc '
  dropdb --force --if-exists --username="$POSTGRES_USER" "$POSTGRES_DB"
  createdb --username="$POSTGRES_USER" "$POSTGRES_DB"
'
docker compose exec -T db sh -lc '
  pg_restore \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --no-owner \
    --no-acl \
    --exit-on-error
' < "$BACKUP_DIR/database.dump"

# Restore the named Docker media volume through the web image.
docker compose run --rm --no-deps -T web sh -lc '
  mkdir -p /app/media
  find /app/media -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  tar -xzf - -C /app
' < "$BACKUP_DIR/media.tar.gz"

docker compose up -d --remove-orphans

healthy=0
for _ in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:8010/health/ >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done
[[ "$healthy" -eq 1 ]] || { docker compose logs --tail=200 web; exit 1; }

docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py migrate --check

echo "Production wurde erfolgreich aus Snapshot $SNAPSHOT_ID wiederhergestellt."
