#!/usr/bin/env bash
set -Eeuo pipefail

telegram_api_call() {
  local method="$1"
  shift
  local response
  response="$(curl --fail-with-body --silent --show-error \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/${method}" \
    "$@")"
  jq -e '.ok == true' <<<"$response" >/dev/null || {
    echo "Telegram API meldet einen Fehler." >&2
    jq -r '.description // "Unbekannter Telegram-Fehler"' <<<"$response" >&2
    return 1
  }
  printf '%s' "$response"
}

telegram_send_message() {
  local text="$1"
  telegram_api_call sendMessage \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${text}" \
    --data-urlencode "disable_web_page_preview=true"
}

telegram_send_document() {
  local path="$1"
  local caption="$2"
  telegram_api_call sendDocument \
    -F "chat_id=${TELEGRAM_CHAT_ID}" \
    -F "document=@${path};type=application/octet-stream" \
    -F "caption=${caption}" \
    -F "disable_content_type_detection=true"
}

telegram_download_file_id() {
  local file_id="$1"
  local target="$2"
  local response file_path
  response="$(telegram_api_call getFile --data-urlencode "file_id=${file_id}")"
  file_path="$(jq -r '.result.file_path // empty' <<<"$response")"
  [[ -n "$file_path" ]] || { echo "Telegram file_path fehlt." >&2; return 1; }
  curl --fail --silent --show-error \
    "https://api.telegram.org/file/bot${TELEGRAM_BOT_TOKEN}/${file_path}" \
    --output "$target"
  test -s "$target"
}
