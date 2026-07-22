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
  local backend="${6:-unknown}"
  local part_count="${7:-0}"
  local timestamp temp
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  temp="$(mktemp "$STATE_DIR/status.XXXXXX")"
  jq -n \
    --arg status "$status" \
    --arg completed_at "$timestamp" \
    --arg snapshot_id "$snapshot_id" \
    --arg git_commit "$git_commit" \
    --arg backend "$backend" \
    --argjson database_bytes "$db_bytes" \
    --argjson media_bytes "$media_bytes" \
    --argjson part_count "$part_count" \
    '{status:$status,completed_at:$completed_at,snapshot_id:$snapshot_id,database_bytes:$database_bytes,media_bytes:$media_bytes,git_commit:$git_commit,backend:$backend,part_count:$part_count}' > "$temp"
  chmod 600 "$temp"
  mv "$temp" "$STATUS_FILE"
}

cleanup() {
  local exit_code=$?
  if [[ "$SUCCESS" -ne 1 ]]; then
    write_status "failure" "" 0 0 "unknown" "${BACKUP_BACKEND:-unknown}" 0
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

BACKUP_BACKEND="${BACKUP_BACKEND:-restic}"
for command in docker flock sha256sum jq tar; do
  command -v "$command" >/dev/null 2>&1 || { echo "$command ist nicht installiert." >&2; exit 1; }
done

case "$BACKUP_BACKEND" in
  restic)
    required=(RESTIC_REPOSITORY RESTIC_PASSWORD AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY)
    for command in restic; do command -v "$command" >/dev/null 2>&1 || { echo "$command ist nicht installiert." >&2; exit 1; }; done
    ;;
  telegram)
    required=(TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID BACKUP_ENCRYPTION_PASSWORD)
    for command in curl gpg split; do command -v "$command" >/dev/null 2>&1 || { echo "$command ist nicht installiert." >&2; exit 1; }; done
    # shellcheck disable=SC1091
    source "$APP_DIR/ops/backup/telegram-lib.sh"
    ;;
  *)
    echo "Unbekanntes BACKUP_BACKEND: $BACKUP_BACKEND" >&2
    exit 1
    ;;
esac
for variable in "${required[@]}"; do
  [[ -n "${!variable:-}" ]] || { echo "$variable fehlt in $BACKUP_ENV" >&2; exit 1; }
done
[[ "$BACKUP_BACKEND" != "telegram" || "${#BACKUP_ENCRYPTION_PASSWORD}" -ge 24 ]] || {
  echo "BACKUP_ENCRYPTION_PASSWORD muss mindestens 24 Zeichen lang sein." >&2
  exit 1
}

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
BACKUP_ID="apluscard-${TIMESTAMP}"
GIT_COMMIT="$(git rev-parse HEAD 2>/dev/null || printf unknown)"
HOST_TAG="${BACKUP_HOST_TAG:-apluscard-production}"

# Portable PostgreSQL 16 dump.
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

# Branch images and all future uploaded media.
docker compose exec -T web tar -C /app -czf - media > "$WORK_DIR/media.tar.gz"
test -s "$WORK_DIR/media.tar.gz" || { echo "Media-Archiv ist leer." >&2; exit 1; }
tar -tzf "$WORK_DIR/media.tar.gz" >/dev/null

# Never sent in plaintext: Restic encrypts it, Telegram mode encrypts the entire bundle with GPG.
install -m 600 .env "$WORK_DIR/production.env"
cat > "$WORK_DIR/metadata.json" <<JSON
{
  "application": "apluscard",
  "backup_id": "$BACKUP_ID",
  "created_at": "$TIMESTAMP",
  "git_commit": "$GIT_COMMIT",
  "postgres_image": "postgres:16-alpine",
  "backend": "$BACKUP_BACKEND",
  "contents": ["database.dump", "media.tar.gz", "production.env"]
}
JSON
(
  cd "$WORK_DIR"
  sha256sum database.dump media.tar.gz production.env metadata.json > SHA256SUMS
)
DB_BYTES="$(stat -c %s "$WORK_DIR/database.dump")"
MEDIA_BYTES="$(stat -c %s "$WORK_DIR/media.tar.gz")"

if [[ "$BACKUP_BACKEND" == "restic" ]]; then
  if ! restic snapshots --no-lock >/dev/null 2>&1; then
    echo "Restic-Repository wird initialisiert."
    restic init
  fi
  restic backup "$WORK_DIR" \
    --host "$HOST_TAG" \
    --tag apluscard \
    --tag production \
    --tag scheduled \
    --exclude-caches
  restic forget \
    --host "$HOST_TAG" \
    --tag apluscard \
    --keep-within 7d \
    --keep-daily 30 \
    --keep-weekly 12 \
    --keep-monthly 12 \
    --keep-yearly 3
  if [[ "$(date -u +%u)" == "7" ]]; then restic prune; fi
  SNAPSHOT_ID="$(restic snapshots --json --host "$HOST_TAG" --tag apluscard | jq -r 'sort_by(.time) | last | .short_id // .id // empty')"
  [[ -n "$SNAPSHOT_ID" ]] || { echo "Neue Snapshot-ID konnte nicht ermittelt werden." >&2; exit 1; }
  write_status "success" "$SNAPSHOT_ID" "$DB_BYTES" "$MEDIA_BYTES" "$GIT_COMMIT" "restic" 0
else
  # Official Telegram Bot API downloads are limited, so every encrypted part stays below 20 MB.
  BUNDLE="$WORK_DIR/${BACKUP_ID}.tar.gz"
  ENCRYPTED="$WORK_DIR/${BACKUP_ID}.tar.gz.gpg"
  PASSPHRASE_FILE="$WORK_DIR/.backup-passphrase"
  printf '%s' "$BACKUP_ENCRYPTION_PASSWORD" > "$PASSPHRASE_FILE"
  chmod 600 "$PASSPHRASE_FILE"
  tar -C "$WORK_DIR" -czf "$BUNDLE" database.dump media.tar.gz production.env metadata.json SHA256SUMS
  gpg --batch --yes --pinentry-mode loopback \
    --passphrase-file "$PASSPHRASE_FILE" \
    --symmetric --cipher-algo AES256 --compress-algo none \
    --output "$ENCRYPTED" "$BUNDLE"
  rm -f "$PASSPHRASE_FILE" "$BUNDLE"
  test -s "$ENCRYPTED" || { echo "Verschlüsseltes Backup ist leer." >&2; exit 1; }

  ENCRYPTED_SHA256="$(sha256sum "$ENCRYPTED" | awk '{print $1}')"
  PART_PREFIX="$WORK_DIR/${BACKUP_ID}."
  split --bytes=18M --numeric-suffixes=1 --suffix-length=4 --additional-suffix=.part "$ENCRYPTED" "$PART_PREFIX"
  rm -f "$ENCRYPTED"
  mapfile -t PARTS < <(find "$WORK_DIR" -maxdepth 1 -type f -name "${BACKUP_ID}.*.part" -printf '%p\n' | sort)
  PART_COUNT="${#PARTS[@]}"
  [[ "$PART_COUNT" -gt 0 ]] || { echo "Keine Telegram-Teile erzeugt." >&2; exit 1; }

  telegram_api_call getMe >/dev/null
  telegram_api_call getChat --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" >/dev/null
  telegram_send_message "🔐 A+ Backup ${BACKUP_ID}\nUpload startet: ${PART_COUNT} verschlüsselte Teile.\nGit: ${GIT_COMMIT:0:12}" >/dev/null

  INDEX="$WORK_DIR/${BACKUP_ID}.index.json"
  jq -n \
    --arg backup_id "$BACKUP_ID" \
    --arg created_at "$TIMESTAMP" \
    --arg git_commit "$GIT_COMMIT" \
    --arg encrypted_sha256 "$ENCRYPTED_SHA256" \
    --argjson part_count "$PART_COUNT" \
    '{version:1,application:"apluscard",backend:"telegram",backup_id:$backup_id,created_at:$created_at,git_commit:$git_commit,encrypted_sha256:$encrypted_sha256,part_count:$part_count,parts:[]}' > "$INDEX"

  counter=0
  for part in "${PARTS[@]}"; do
    counter=$((counter + 1))
    name="$(basename "$part")"
    bytes="$(stat -c %s "$part")"
    part_sha="$(sha256sum "$part" | awk '{print $1}')"
    response="$(telegram_send_document "$part" "${BACKUP_ID} · Teil ${counter}/${PART_COUNT}")"
    file_id="$(jq -r '.result.document.file_id // empty' <<<"$response")"
    message_id="$(jq -r '.result.message_id // empty' <<<"$response")"
    [[ -n "$file_id" && -n "$message_id" ]] || { echo "Telegram-Dateimetadaten fehlen." >&2; exit 1; }
    jq \
      --arg name "$name" \
      --arg sha256 "$part_sha" \
      --arg file_id "$file_id" \
      --argjson bytes "$bytes" \
      --argjson message_id "$message_id" \
      '.parts += [{name:$name,sha256:$sha256,bytes:$bytes,file_id:$file_id,message_id:$message_id}]' \
      "$INDEX" > "$INDEX.tmp"
    mv "$INDEX.tmp" "$INDEX"
  done

  index_response="$(telegram_send_document "$INDEX" "${BACKUP_ID} · Wiederherstellungsindex")"
  index_message_id="$(jq -r '.result.message_id // empty' <<<"$index_response")"
  jq --argjson index_message_id "$index_message_id" '.index_message_id=$index_message_id' "$INDEX" > "$INDEX.tmp"
  mv "$INDEX.tmp" "$INDEX"
  install -m 600 "$INDEX" "$STATE_DIR/last-telegram-index.json"
  telegram_send_message "✅ A+ Backup ${BACKUP_ID} vollständig.\nTeile: ${PART_COUNT}\nSHA-256: ${ENCRYPTED_SHA256}\nIndex-Nachricht: ${index_message_id}" >/dev/null

  write_status "success" "$BACKUP_ID" "$DB_BYTES" "$MEDIA_BYTES" "$GIT_COMMIT" "telegram" "$PART_COUNT"
fi

SUCCESS=1
echo "Backup erfolgreich: ${BACKUP_ID} über ${BACKUP_BACKEND}"
