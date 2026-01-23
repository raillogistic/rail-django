#!/bin/sh

# Default to 24 hours if not set
INTERVAL=${BACKUP_FREQUENCY_HOURS:-24}
echo "Starting backup service. Frequency: Every $INTERVAL hours."

# DATABASE_URL format: postgres://user:password@host:port/dbname
if [ -z "$DATABASE_URL" ]; then
    echo "Error: DATABASE_URL is required for backups."
    exit 1
fi

while true; do
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    FILENAME="/backups/backup_${TIMESTAMP}.sql.gz"

    echo "[$TIMESTAMP] Starting backup..."

    if pg_dump --dbname="$DATABASE_URL" | gzip > "$FILENAME"; then
        echo "[$TIMESTAMP] Backup successful: $FILENAME"
        
        # Optional: Delete backups older than 30 days
        find /backups -name "backup_*.sql.gz" -mtime +30 -delete
    else
        echo "[$TIMESTAMP] Backup FAILED!"
    fi

    # Wait for the next interval (convert hours to seconds)
    sleep $(($INTERVAL * 3600))
done
