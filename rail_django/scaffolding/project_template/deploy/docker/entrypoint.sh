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
scheme = (parsed.scheme or "").lower()

if not host:
    if scheme in {"sqlite", "sqlite3"}:
        print("skip")
        sys.exit(0)
    sys.exit(1)

if port is None:
    defaults = {
        "postgres": 5432,
        "postgresql": 5432,
        "mysql": 3306,
        "mariadb": 3306,
        "mssql": 1433,
    }
    port = defaults.get(scheme)
    if port is None:
        sys.exit(1)

print(f"{host}:{port}")
PY
    ) || {
        echo "Error: DATABASE_URL must include a host and port (or use a supported scheme default)."
        exit 1
    }

    if [ "$DB_INFO" = "skip" ]; then
        echo "Skipping database wait (no host/port to check)."
    else
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
fi

if is_truthy "${RUN_MIGRATIONS:-false}"; then
    echo "Running migrations..."
    python manage.py migrate
fi

if [ "${RAIL_METADATA_DEPLOY_VERSION_MODE:-}" = "command" ]; then
    echo "Bumping metadata deploy version..."
    python manage.py bump_metadata_deploy_version
fi

if is_truthy "${RUN_COLLECTSTATIC:-false}"; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

if is_truthy "${DJANGO_CHECK_DEPLOY:-false}"; then
    echo "Running Django system checks..."
    python manage.py check --deploy
fi

echo "Starting server..."
SERVER_MODE=${DJANGO_SERVER_MODE:-asgi}

# ─────────────────────────────────────────────────────────────────────────────
# WSGI mode — Gunicorn with gthread worker (synchronous)
# ─────────────────────────────────────────────────────────────────────────────
if [ "$SERVER_MODE" = "wsgi" ]; then
    echo "Starting WSGI server (gunicorn + gthread)..."
    WORKERS=${GUNICORN_WORKERS:-3}
    THREADS=${GUNICORN_THREADS:-4}
    TIMEOUT=${GUNICORN_TIMEOUT:-30}
    GRACEFUL_TIMEOUT=${GUNICORN_GRACEFUL_TIMEOUT:-30}
    KEEPALIVE=${GUNICORN_KEEPALIVE:-5}
    MAX_REQUESTS=${GUNICORN_MAX_REQUESTS:-1000}
    MAX_REQUESTS_JITTER=${GUNICORN_MAX_REQUESTS_JITTER:-100}
    ACCESS_LOG=${GUNICORN_ACCESS_LOG:--}
    ERROR_LOG=${GUNICORN_ERROR_LOG:--}
    LOG_LEVEL=${GUNICORN_LOG_LEVEL:-info}
    BIND_HOST=${ASGI_BIND:-0.0.0.0}
    BIND_PORT=${ASGI_PORT:-8000}
    WSGI_MODULE=${DJANGO_WSGI_MODULE:-root.wsgi:application}

    exec gunicorn "$WSGI_MODULE" \
        --bind "${BIND_HOST}:${BIND_PORT}" \
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
fi

# ─────────────────────────────────────────────────────────────────────────────
# ASGI mode — Gunicorn + Uvicorn workers (recommended for production)
#
# Architecture: Gunicorn acts as process manager, Uvicorn handles the
# async event loop per worker. This gives:
#   • Multi-process with pre-fork (graceful restarts, memory isolation)
#   • uvloop-based event loop (2-5x faster than asyncio default)
#   • httptools HTTP parsing (C-based, near zero overhead)
#   • Automatic worker recycling via max-requests
#   • Keep-alive connection reuse with Nginx upstream
#
# Falls back to standalone Uvicorn if Gunicorn is unavailable.
# Falls back to Daphne if neither Uvicorn nor Gunicorn is available.
# ─────────────────────────────────────────────────────────────────────────────
ASGI_BIND=${ASGI_BIND:-0.0.0.0}
ASGI_PORT=${ASGI_PORT:-8000}
ASGI_MODULE=${DJANGO_ASGI_MODULE:-root.asgi:application}
ASGI_VERBOSITY=${ASGI_VERBOSITY:-1}
WORKERS=${UVICORN_WORKERS:-$(python -c "import os; print(min(max(os.cpu_count() or 2, 2) * 2 + 1, 9))")}
TIMEOUT=${UVICORN_TIMEOUT:-30}
KEEPALIVE=${UVICORN_KEEPALIVE:-5}
MAX_REQUESTS=${UVICORN_MAX_REQUESTS:-2000}
MAX_REQUESTS_JITTER=${UVICORN_MAX_REQUESTS_JITTER:-200}
LIMIT_CONCURRENCY=${UVICORN_LIMIT_CONCURRENCY:-200}
BACKLOG=${UVICORN_BACKLOG:-2048}
ACCESS_LOG=${UVICORN_ACCESS_LOG:--}
ERROR_LOG=${UVICORN_ERROR_LOG:--}
LOG_LEVEL=${UVICORN_LOG_LEVEL:-info}

# Prefer Gunicorn + UvicornWorker (best multi-process ASGI setup)
if python -c "import gunicorn" 2>/dev/null && python -c "import uvicorn" 2>/dev/null; then
    echo "Starting ASGI server (gunicorn + uvicorn.workers.UvicornWorker)..."
    echo "  Workers: ${WORKERS} | Keepalive: ${KEEPALIVE}s | Max-requests: ${MAX_REQUESTS}"

    exec gunicorn "$ASGI_MODULE" \
        --bind "${ASGI_BIND}:${ASGI_PORT}" \
        --workers "$WORKERS" \
        --worker-class uvicorn.workers.UvicornWorker \
        --timeout "$TIMEOUT" \
        --graceful-timeout "$TIMEOUT" \
        --keep-alive "$KEEPALIVE" \
        --max-requests "$MAX_REQUESTS" \
        --max-requests-jitter "$MAX_REQUESTS_JITTER" \
        --backlog "$BACKLOG" \
        --access-logfile "$ACCESS_LOG" \
        --error-logfile "$ERROR_LOG" \
        --log-level "$LOG_LEVEL" \
        --preload
fi

# Fallback: standalone Uvicorn (still excellent, but no process manager)
if python -c "import uvicorn" 2>/dev/null; then
    echo "Starting ASGI server (uvicorn standalone)..."
    echo "  Workers: ${WORKERS} | Keepalive: ${KEEPALIVE}s | Concurrency limit: ${LIMIT_CONCURRENCY}"

    exec uvicorn "$ASGI_MODULE" \
        --host "$ASGI_BIND" \
        --port "$ASGI_PORT" \
        --workers "$WORKERS" \
        --loop uvloop \
        --http httptools \
        --timeout-keep-alive "$KEEPALIVE" \
        --limit-concurrency "$LIMIT_CONCURRENCY" \
        --backlog "$BACKLOG" \
        --log-level "$LOG_LEVEL" \
        --no-access-log
fi

# Final fallback: Daphne (legacy, single-threaded)
echo "WARNING: Neither uvicorn nor gunicorn+uvicorn found. Falling back to Daphne."
echo "WARNING: Daphne is single-threaded and significantly slower. Install uvicorn[standard] for production."
echo "Starting ASGI server (daphne — fallback)..."
exec daphne \
    -b "$ASGI_BIND" \
    -p "$ASGI_PORT" \
    -v "$ASGI_VERBOSITY" \
    "$ASGI_MODULE"
