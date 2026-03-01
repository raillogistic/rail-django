#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env.prod"

die() {
  echo "[backup] Error: $*" >&2
  exit 1
}

note() {
  echo "[backup] $*"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

read_env() {
  local key="$1"
  local line
  line="$(grep -E "^[[:space:]]*${key}=" "$ENV_FILE" | tail -n 1 || true)"
  if [ -z "$line" ]; then
    echo ""
    return 0
  fi
  local value="${line#*=}"
  value="${value%$'\r'}"
  echo "$value"
}

is_number() {
  case "$1" in
    ''|*[!0-9]*)
      return 1
      ;;
    *)
      return 0
      ;;
  esac
}

extract_client_major() {
  pg_dump --version 2>/dev/null | awk '
    {
      for (i = 1; i <= NF; i++) {
        if ($i ~ /^[0-9]+(\.[0-9]+)?/) {
          split($i, parts, ".")
          print parts[1]
          exit
        }
      }
    }
  '
}

ensure_backup_client_is_compatible() {
  local client_major server_version_num server_major
  client_major="$(extract_client_major)"
  server_version_num="$(psql "$DATABASE_URL" -Atqc "SHOW server_version_num;" 2>/dev/null || true)"

  if ! is_number "$client_major"; then
    note "Warning: Could not determine pg_dump major version; skipping compatibility check."
    return 0
  fi
  if ! is_number "$server_version_num"; then
    note "Warning: Could not determine PostgreSQL server version; skipping compatibility check."
    return 0
  fi

  server_major=$((server_version_num / 10000))
  if [ "$client_major" -lt "$server_major" ]; then
    die "pg_dump major version ($client_major) is older than server major ($server_major)."
  fi
}

require_cmd pg_dump
require_cmd psql
require_cmd date

if [ ! -f "$ENV_FILE" ]; then
  die ".env.prod not found. Create $ENV_FILE and rerun."
fi

DATABASE_URL="$(read_env DATABASE_URL)"
if [ -z "$DATABASE_URL" ]; then
  die "DATABASE_URL is required in .env.prod."
fi

BACKUP_PATH="$(read_env BACKUP_PATH)"
BACKUP_PATH="${BACKUP_PATH:-backups}"
if [[ "$BACKUP_PATH" != /* ]]; then
  BACKUP_PATH="$PROJECT_ROOT/$BACKUP_PATH"
fi
mkdir -p "$BACKUP_PATH"

BACKUP_RETENTION_DAYS="$(read_env BACKUP_RETENTION_DAYS)"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

ensure_backup_client_is_compatible

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="$BACKUP_PATH/backup_${TIMESTAMP}.dump"

note "Starting backup..."
pg_dump \
  --format=custom \
  --compress=9 \
  --no-owner \
  --no-privileges \
  --dbname="$DATABASE_URL" \
  --file="$BACKUP_FILE"
note "Backup created: $BACKUP_FILE"

if is_number "$BACKUP_RETENTION_DAYS"; then
  find "$BACKUP_PATH" -name "backup_*.dump" -mtime +"$BACKUP_RETENTION_DAYS" -delete
fi

note "Done."
