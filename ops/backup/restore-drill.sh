#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/root/apluscard}"
BACKUP_ENV="${BACKUP_ENV:-$APP_DIR/.backup.env}"
STATE_DIR="${BACKUP_STATE_DIR:-/var/lib/apluscard-backup}"
STATUS_FILE="$STATE_DIR/last-restore-drill.json"
LOCK_FILE="${RESTORE_DRILL_LOCK_FILE:-/var/lock/apluscard-restore-drill.lock}"
RESTORE_DIR=""
TEST_DB=""
SUCCESS=0

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

write_status() {
  local status="$1"
  local snapshot_id="${2:-}"
  local migrations="${3:-0}"
  local wallets="${4:-0}"
  local timestamp temp
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  temp="$(mktemp "$STATE_DIR/drill.XXXXXX")"
  cat > "$temp" <<JSON
{"status":"$status","completed_at":"$timestamp","snapshot_id":"$snapshot_id","django_migrations":$migrations,"wallets":$wallets}
JSON
  chmod 600 "$temp"
  mv "$temp" "$STATUS_FILE"
}

cleanup() {
  local exit_code=$?
  if [[ -n "$TEST_DB" ]]; then
    cd "$APP_DIR" 2>/dev/null || true
    docker compose exec -T db sh -lc 'dropdb --if-exists --username="$POSTGRES_USER" "$1"' sh "$TEST_DB" >/dev/null 2>&1 || true
  fi
  [[ -n "$RESTORE_DIR" && -d "$RESTORE_DIR" ]] && rm -rf "$RESTORE_DIR"
  if [[ "$SUCCESS" -ne 1 ]]; then
    write_status "failure"
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
flock -n 9 || { echo "Ein Restore-Test läuft bereits."; SUCCESS=1; exit 0; }

cd "$APP_DIR"
docker compose ps --status running db | grep -q db || { echo "PostgreSQL-Container läuft nicht." >&2; exit 1; }

HOST_TAG="${BACKUP_HOST_TAG:-apluscard-production}"
SNAPSHOT_ID="$(restic snapshots --json --host "$HOST_TAG" --tag apluscard | jq -r 'sort_by(.time) | last | .short_id // .id // empty')"
[[ -n "$SNAPSHOT_ID" ]] || { echo "Kein Apluscard-Backup gefunden." >&2; exit 1; }

RESTORE_DIR="$(mktemp -d "$STATE_DIR/restore-drill.XXXXXX")"
chmod 700 "$RESTORE_DIR"
restic restore "$SNAPSHOT_ID" --target "$RESTORE_DIR"

BACKUP_DIR="$(find "$RESTORE_DIR" -type f -name database.dump -printf '%h\n' | head -n 1)"
[[ -n "$BACKUP_DIR" ]] || { echo "database.dump fehlt im Snapshot." >&2; exit 1; }

(
  cd "$BACKUP_DIR"
  sha256sum -c SHA256SUMS
  tar -tzf media.tar.gz >/dev/null
)

TEST_DB="apluscard_restore_$(date -u +%Y%m%d%H%M%S)_$RANDOM"
docker compose exec -T db sh -lc 'createdb --username="$POSTGRES_USER" "$1"' sh "$TEST_DB"
docker compose exec -T db sh -lc 'pg_restore --username="$POSTGRES_USER" --dbname="$1" --no-owner --no-acl --exit-on-error' sh "$TEST_DB" < "$BACKUP_DIR/database.dump"

MIGRATIONS="$(docker compose exec -T db sh -lc 'psql --username="$POSTGRES_USER" --dbname="$1" --tuples-only --no-align --command="SELECT COUNT(*) FROM django_migrations"' sh "$TEST_DB" | tr -d '[:space:]')"
WALLETS="$(docker compose exec -T db sh -lc 'psql --username="$POSTGRES_USER" --dbname="$1" --tuples-only --no-align --command="SELECT COUNT(*) FROM cards_wallet"' sh "$TEST_DB" | tr -d '[:space:]')"

[[ "$MIGRATIONS" =~ ^[0-9]+$ && "$MIGRATIONS" -gt 0 ]] || { echo "Restore enthält keine Django-Migrationen." >&2; exit 1; }
[[ "$WALLETS" =~ ^[0-9]+$ ]] || { echo "Wallet-Anzahl konnte nicht geprüft werden." >&2; exit 1; }

write_status "success" "$SNAPSHOT_ID" "$MIGRATIONS" "$WALLETS"
SUCCESS=1

echo "Restore-Drill erfolgreich: Snapshot $SNAPSHOT_ID, Migrationen $MIGRATIONS, Wallets $WALLETS"
