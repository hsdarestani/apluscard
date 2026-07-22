#!/usr/bin/env bash
set -Eeuo pipefail

telegram_unpack_parts() {
  local index_file="$1"
  local parts_dir="$2"
  local output_dir="$3"
  local encrypted="$output_dir/backup.tar.gz.gpg"
  local bundle="$output_dir/backup.tar.gz"
  local passphrase_file="$output_dir/.backup-passphrase"

  mkdir -p "$output_dir"
  chmod 700 "$output_dir"
  jq -e '.version == 1 and .backend == "telegram" and (.parts | length) == .part_count' "$index_file" >/dev/null

  : > "$encrypted"
  while IFS=$'\t' read -r name expected_sha expected_bytes; do
    local part="$parts_dir/$name"
    [[ -s "$part" ]] || { echo "Telegram-Teil fehlt: $name" >&2; return 1; }
    [[ "$(stat -c %s "$part")" == "$expected_bytes" ]] || { echo "Falsche Größe: $name" >&2; return 1; }
    [[ "$(sha256sum "$part" | awk '{print $1}')" == "$expected_sha" ]] || { echo "Hash-Fehler: $name" >&2; return 1; }
    cat "$part" >> "$encrypted"
  done < <(jq -r '.parts[] | [.name,.sha256,(.bytes|tostring)] | @tsv' "$index_file")

  expected_encrypted_sha="$(jq -r '.encrypted_sha256' "$index_file")"
  [[ "$(sha256sum "$encrypted" | awk '{print $1}')" == "$expected_encrypted_sha" ]] || {
    echo "Hash des zusammengesetzten Backups stimmt nicht." >&2
    return 1
  }

  printf '%s' "$BACKUP_ENCRYPTION_PASSWORD" > "$passphrase_file"
  chmod 600 "$passphrase_file"
  gpg --batch --yes --pinentry-mode loopback \
    --passphrase-file "$passphrase_file" \
    --decrypt --output "$bundle" "$encrypted"
  rm -f "$passphrase_file" "$encrypted"
  test -s "$bundle"
  tar -xzf "$bundle" -C "$output_dir"
  rm -f "$bundle"

  (
    cd "$output_dir"
    sha256sum -c SHA256SUMS
    tar -tzf media.tar.gz >/dev/null
    test -s database.dump
    test -s production.env
    test -s metadata.json
  )
}

telegram_download_index_parts() {
  local index_file="$1"
  local target_dir="$2"
  mkdir -p "$target_dir"
  chmod 700 "$target_dir"
  while IFS=$'\t' read -r name file_id; do
    telegram_download_file_id "$file_id" "$target_dir/$name"
  done < <(jq -r '.parts[] | [.name,.file_id] | @tsv' "$index_file")
}
