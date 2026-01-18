#!/bin/sh
set -e

: "${DJANGO_SETTINGS_MODULE:=root.settings.production}"
export DJANGO_SETTINGS_MODULE

is_truthy() {
    case "$(echo "$1" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|y|on) return 0 ;;
        *) return 1 ;;
    esac
}

# Wait for database
if [ "$DATABASE_URL" ]; then
    echo "Waiting for database..."

    if ! command -v nc >/dev/null 2>&1; then
        echo "Error: nc is required to check database availability."
        exit 1
    fi

    DB_INFO=$(python - <<'PY'
import os
import sys
from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL", "")
parsed = urlparse(url)
host = parsed.hostname
port = parsed.port
if not host or not port:
    sys.exit(1)
print(f"{host}:{port}")
PY
    ) || {
        echo "Error: DATABASE_URL must include host and port."
        exit 1
    }

    DB_HOST=${DB_INFO%:*}
    DB_PORT=${DB_INFO##*:}
    DB_WAIT_TIMEOUT=${DB_WAIT_TIMEOUT:-30}
    DB_WAIT_INTERVAL=${DB_WAIT_INTERVAL:-1}
    START_TIME=$(date +%s)

    while ! nc -z -w 1 "$DB_HOST" "$DB_PORT"; do
        NOW=$(date +%s)
        if [ $((NOW - START_TIME)) -ge "$DB_WAIT_TIMEOUT" ]; then
            echo "Error: Database not reachable after ${DB_WAIT_TIMEOUT}s."
            exit 1
        fi
        sleep "$DB_WAIT_INTERVAL"
    done

    echo "Database started"
fi

if is_truthy "${RUN_MIGRATIONS:-true}"; then
    echo "Running migrations..."
    python manage.py migrate
fi

if is_truthy "${RUN_COLLECTSTATIC:-true}"; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

if is_truthy "${DJANGO_CHECK_DEPLOY:-false}"; then
    echo "Running Django system checks..."
    python manage.py check --deploy
fi

echo "Starting server..."
# Optimization:
# - workers: Automatic based on CPU (usually 2*cores + 1) or configurable
# - threads: 4 threads per worker handles I/O waiting better than sync workers
# - preload: Loads code once before forking, saving RAM and starting faster
# - worker-class: gthread enables threading
WORKERS=${GUNICORN_WORKERS:-3}
THREADS=${GUNICORN_THREADS:-4}
TIMEOUT=${GUNICORN_TIMEOUT:-30}
GRACEFUL_TIMEOUT=${GUNICORN_GRACEFUL_TIMEOUT:-30}
KEEPALIVE=${GUNICORN_KEEPALIVE:-2}
MAX_REQUESTS=${GUNICORN_MAX_REQUESTS:-1000}
MAX_REQUESTS_JITTER=${GUNICORN_MAX_REQUESTS_JITTER:-100}
ACCESS_LOG=${GUNICORN_ACCESS_LOG:--}
ERROR_LOG=${GUNICORN_ERROR_LOG:--}
LOG_LEVEL=${GUNICORN_LOG_LEVEL:-info}
WSGI_MODULE=${DJANGO_WSGI_MODULE:-root.wsgi:application}

exec gunicorn "$WSGI_MODULE" \
    --bind 0.0.0.0:8000 \
    --workers $WORKERS \
    --threads $THREADS \
    --worker-class gthread \
    --timeout $TIMEOUT \
    --graceful-timeout $GRACEFUL_TIMEOUT \
    --keep-alive $KEEPALIVE \
    --max-requests $MAX_REQUESTS \
    --max-requests-jitter $MAX_REQUESTS_JITTER \
    --access-logfile "$ACCESS_LOG" \
    --error-logfile "$ERROR_LOG" \
    --log-level "$LOG_LEVEL" \
    --preload
