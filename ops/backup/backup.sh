#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/root/apluscard}"
BACKUP_ENV="${BACKUP_ENV:-$APP_DIR/.backup.env}"
STATE_DIR="${BACKUP_STATE_DIR:-/var/lib/apluscard-backup}"
STATUS_FILE="$STATE_DIR/last-backup.json"
LOCK_FILE="${BACKUP_LOCK_FILE:-/var/lock/apluscard-backup.lock}"
SUCCESS=0
WORK_DIR=""

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

write_status() {
  local status="$1"
  local snapshot_id="${2:-}"
  local db_bytes="${3:-0}"
  local media_bytes="${4:-0}"
  local git_commit="${5:-unknown}"
  local timestamp
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  local temp
  temp="$(mktemp "$STATE_DIR/status.XXXXXX")"
  cat > "$temp" <<JSON
{"status":"$status","completed_at":"$timestamp","snapshot_id":"$snapshot_id","database_bytes":$db_bytes,"media_bytes":$media_bytes,"git_commit":"$git_commit"}
JSON
  chmod 600 "$temp"
  mv "$temp" "$STATUS_FILE"
}

cleanup() {
  local exit_code=$?
  if [[ "$SUCCESS" -ne 1 ]]; then
    write_status "failure"
  fi
  if [[ -n "$WORK_DIR" && -d "$WORK_DIR" ]]; then
    rm -rf "$WORK_DIR"
  fi
  exit "$exit_code"
}
trap cleanup EXIT

[[ -f "$BACKUP_ENV" ]] || { echo "Backup-Konfiguration fehlt: $BACKUP_ENV" >&2; exit 1; }
# shellcheck disable=SC1090
set -a
source "$BACKUP_ENV"
set +a

required=(RESTIC_REPOSITORY RESTIC_PASSWORD AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY)
for variable in "${required[@]}"; do
  [[ -n "${!variable:-}" ]] || { echo "$variable fehlt in $BACKUP_ENV" >&2; exit 1; }
done

for command in docker restic flock sha256sum jq; do
  command -v "$command" >/dev/null 2>&1 || { echo "$command ist nicht installiert." >&2; exit 1; }
done

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Ein Backup läuft bereits; dieser Lauf wird beendet."
  SUCCESS=1
  exit 0
fi

cd "$APP_DIR"
[[ -f docker-compose.yml ]] || { echo "docker-compose.yml fehlt in $APP_DIR" >&2; exit 1; }
[[ -f .env ]] || { echo "Production-.env fehlt in $APP_DIR" >&2; exit 1; }

docker compose ps --status running db | grep -q db || { echo "PostgreSQL-Container läuft nicht." >&2; exit 1; }
docker compose ps --status running web | grep -q web || { echo "Web-Container läuft nicht." >&2; exit 1; }

WORK_DIR="$(mktemp -d "$STATE_DIR/run.XXXXXX")"
chmod 700 "$WORK_DIR"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
GIT_COMMIT="$(git rev-parse HEAD 2>/dev/null || printf unknown)"
HOST_TAG="${BACKUP_HOST_TAG:-apluscard-production}"

# PostgreSQL logical backup: portable across a fresh PostgreSQL 16 installation.
docker compose exec -T db sh -lc '
  exec pg_dump \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=custom \
    --no-owner \
    --no-acl
' > "$WORK_DIR/database.dump"

test -s "$WORK_DIR/database.dump" || { echo "Datenbank-Dump ist leer." >&2; exit 1; }
docker compose exec -T db pg_restore --list < "$WORK_DIR/database.dump" >/dev/null

# Uploaded branch images and all future customer-uploaded media.
docker compose exec -T web tar -C /app -czf - media > "$WORK_DIR/media.tar.gz"
test -s "$WORK_DIR/media.tar.gz" || { echo "Media-Archiv ist leer." >&2; exit 1; }
tar -tzf "$WORK_DIR/media.tar.gz" >/dev/null

# The production configuration contains secrets, but Restic encrypts every byte
# before it leaves the server. The separate Restic password remains in GitHub Secrets.
install -m 600 .env "$WORK_DIR/production.env"

cat > "$WORK_DIR/metadata.json" <<JSON
{
  "application": "apluscard",
  "created_at": "$TIMESTAMP",
  "git_commit": "$GIT_COMMIT",
  "postgres_image": "postgres:16-alpine",
  "contents": ["database.dump", "media.tar.gz", "production.env"]
}
JSON

(
  cd "$WORK_DIR"
  sha256sum database.dump media.tar.gz production.env metadata.json > SHA256SUMS
)

if ! restic snapshots --no-lock >/dev/null 2>&1; then
  echo "Restic-Repository wird initialisiert."
  restic init
fi

restic backup "$WORK_DIR" \
  --host "$HOST_TAG" \
  --tag apluscard \
  --tag production \
  --tag daily \
  --exclude-caches

restic forget \
  --host "$HOST_TAG" \
  --tag apluscard \
  --keep-daily 14 \
  --keep-weekly 8 \
  --keep-monthly 12 \
  --keep-yearly 3

# Pruning is intentionally weekly because it can be I/O intensive.
if [[ "$(date -u +%u)" == "7" ]]; then
  restic prune
fi

SNAPSHOT_ID="$(restic snapshots --json --latest 1 --host "$HOST_TAG" --tag apluscard | jq -r '.[0].short_id // .[0].id // empty')"
[[ -n "$SNAPSHOT_ID" ]] || { echo "Neue Snapshot-ID konnte nicht ermittelt werden." >&2; exit 1; }

DB_BYTES="$(stat -c %s "$WORK_DIR/database.dump")"
MEDIA_BYTES="$(stat -c %s "$WORK_DIR/media.tar.gz")"
write_status "success" "$SNAPSHOT_ID" "$DB_BYTES" "$MEDIA_BYTES" "$GIT_COMMIT"
SUCCESS=1

echo "Backup erfolgreich: Snapshot $SNAPSHOT_ID"
