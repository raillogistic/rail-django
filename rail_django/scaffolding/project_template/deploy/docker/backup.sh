#!/bin/sh

# Default to 24 hours if not set
INTERVAL=${BACKUP_FREQUENCY_HOURS:-24}
echo "Starting backup service. Frequency: Every $INTERVAL hours."

# DATABASE_URL format: postgres://user:password@host:port/dbname
if [ -z "$DATABASE_URL" ]; then
    echo "Error: DATABASE_URL is required for backups."
    exit 1
fi

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
    CLIENT_MAJOR=$(extract_client_major)
    SERVER_VERSION_NUM=$(psql "$DATABASE_URL" -Atqc "SHOW server_version_num;" 2>/dev/null || true)

    if ! is_number "$CLIENT_MAJOR"; then
        echo "Warning: Could not determine pg_dump major version; skipping compatibility check."
        return 0
    fi
    if ! is_number "$SERVER_VERSION_NUM"; then
        echo "Warning: Could not determine PostgreSQL server version; skipping compatibility check."
        return 0
    fi

    SERVER_MAJOR=$(($SERVER_VERSION_NUM / 10000))
    if [ "$CLIENT_MAJOR" -lt "$SERVER_MAJOR" ]; then
        echo "Error: pg_dump major version ($CLIENT_MAJOR) is older than server major ($SERVER_MAJOR)."
        echo "Set BACKUP_POSTGRES_IMAGE to postgres:${SERVER_MAJOR}-alpine (or newer) and restart backup."
        exit 1
    fi
}

ensure_backup_client_is_compatible

while true; do
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    RAW_FILE="/backups/backup_${TIMESTAMP}.sql"
    FILENAME="${RAW_FILE}.gz"

    echo "[$TIMESTAMP] Starting backup..."

    if pg_dump --dbname="$DATABASE_URL" > "$RAW_FILE"; then
        if gzip -f "$RAW_FILE"; then
            echo "[$TIMESTAMP] Backup successful: $FILENAME"

            # Optional: Delete backups older than 30 days
            find /backups -name "backup_*.sql.gz" -mtime +30 -delete
        else
            echo "[$TIMESTAMP] Backup FAILED during compression."
            rm -f "$RAW_FILE" "$FILENAME"
        fi
    else
        echo "[$TIMESTAMP] Backup FAILED during pg_dump."
        rm -f "$RAW_FILE" "$FILENAME"
    fi

    # Wait for the next interval (convert hours to seconds)
    sleep $(($INTERVAL * 3600))
done
