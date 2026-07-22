#!/usr/bin/env bash
# Shared validation for encrypted Restic backup backends.
# shellcheck shell=bash

backup_require_variable() {
  local variable="$1"
  [[ -n "${!variable:-}" ]] || {
    echo "$variable fehlt in der Backup-Konfiguration." >&2
    return 1
  }
}

backup_require_command() {
  local command="$1"
  command -v "$command" >/dev/null 2>&1 || {
    echo "$command ist nicht installiert." >&2
    return 1
  }
}

backup_configure_backend() {
  backup_require_variable RESTIC_REPOSITORY
  backup_require_variable RESTIC_PASSWORD

  backup_require_command restic

  case "$RESTIC_REPOSITORY" in
    s3:*)
      BACKUP_BACKEND_TYPE="s3"
      backup_require_variable AWS_ACCESS_KEY_ID
      backup_require_variable AWS_SECRET_ACCESS_KEY
      ;;
    rclone:*)
      BACKUP_BACKEND_TYPE="rclone"
      backup_require_variable RCLONE_CONFIG
      [[ -f "$RCLONE_CONFIG" ]] || {
        echo "Rclone-Konfiguration fehlt: $RCLONE_CONFIG" >&2
        return 1
      }
      backup_require_command rclone

      local remote_spec remote_name
      remote_spec="${RESTIC_REPOSITORY#rclone:}"
      remote_name="${remote_spec%%:*}"
      [[ -n "$remote_name" && "$remote_name" != "$remote_spec" ]] || {
        echo "Ungültiges Rclone-Restic-Ziel: $RESTIC_REPOSITORY" >&2
        return 1
      }
      rclone --config "$RCLONE_CONFIG" listremotes | grep -Fxq "${remote_name}:" || {
        echo "Rclone-Remote ${remote_name}: ist nicht konfiguriert." >&2
        return 1
      }
      ;;
    *)
      echo "RESTIC_REPOSITORY muss mit s3: oder rclone: beginnen." >&2
      return 1
      ;;
  esac

  export BACKUP_BACKEND_TYPE
}
