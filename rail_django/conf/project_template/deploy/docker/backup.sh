#!/bin/sh

# Default to 24 hours if not set
INTERVAL=${BACKUP_FREQUENCY_HOURS:-24}
echo "Starting backup service. Frequency: Every $INTERVAL hours."

# Extract connection details from DATABASE_URL if not provided explicitly
# DATABASE_URL format: postgres://user:password@host:port/dbname
if [ -z "$PGHOST" ] && [ "$DATABASE_URL" ]; then
    export PGUSER=$(echo $DATABASE_URL | sed -r 's/.*:\/\/(.*):(.*)@(.*):(.*)\/(.*)/\1/')
    export PGPASSWORD=$(echo $DATABASE_URL | sed -r 's/.*:\/\/(.*):(.*)@(.*):(.*)\/(.*)/\2/')
    export PGHOST=$(echo $DATABASE_URL | sed -r 's/.*:\/\/(.*):(.*)@(.*):(.*)\/(.*)/\3/')
    export PGPORT=$(echo $DATABASE_URL | sed -r 's/.*:\/\/(.*):(.*)@(.*):(.*)\/(.*)/\4/')
    export PGDATABASE=$(echo $DATABASE_URL | sed -r 's/.*:\/\/(.*):(.*)@(.*):(.*)\/(.*)/\5/')
fi

while true; do
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    FILENAME="/backups/backup_${TIMESTAMP}.sql.gz"

    echo "[$TIMESTAMP] Starting backup of $PGDATABASE from $PGHOST..."

    if pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" | gzip > "$FILENAME"; then
        echo "[$TIMESTAMP] Backup successful: $FILENAME"
        
        # Optional: Delete backups older than 30 days
        find /backups -name "backup_*.sql.gz" -mtime +30 -delete
    else
        echo "[$TIMESTAMP] Backup FAILED!"
    fi

    # Wait for the next interval (convert hours to seconds)
    sleep $(($INTERVAL * 3600))
done
