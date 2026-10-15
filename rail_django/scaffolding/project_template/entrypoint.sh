#!/bin/sh
set -e

echo "running container"
cd /home/app

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-root.settings.production}"

# Create logs directory and empty log files if they don't exist
# This prevents Django from crashing on startup due to missing files
mkdir -p logs
touch logs/django.log logs/security.log logs/audit.log logs/celery.log

is_true() {
    case "${1:-}" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

if is_true "${RUN_COLLECTSTATIC:-false}"; then
    python manage.py collectstatic --noinput
fi

if is_true "${RUN_MIGRATIONS:-false}"; then
    python manage.py migrate
fi

if [ "${DJANGO_SERVER_MODE:-asgi}" = "wsgi" ]; then
    exec gunicorn "${DJANGO_WSGI_MODULE:-root.wsgi:application}" \
        --bind "${GUNICORN_BIND:-0.0.0.0:8000}" \
        --workers "${GUNICORN_WORKERS:-3}" \
        --threads "${GUNICORN_THREADS:-4}" \
        --timeout "${GUNICORN_TIMEOUT:-30}"
fi

exec gunicorn "${DJANGO_ASGI_MODULE:-root.asgi:application}" \
    --bind "${ASGI_BIND:-0.0.0.0}:${ASGI_PORT:-8000}" \
    --worker-class uvicorn_worker.UvicornWorker \
    --workers "${UVICORN_WORKERS:-4}" \
    --timeout "${UVICORN_TIMEOUT:-30}" \
    --keep-alive "${UVICORN_KEEPALIVE:-5}" \
    --max-requests "${UVICORN_MAX_REQUESTS:-2000}" \
    --max-requests-jitter "${UVICORN_MAX_REQUESTS_JITTER:-200}" \
    --backlog "${UVICORN_BACKLOG:-2048}" \
    --log-level "${UVICORN_LOG_LEVEL:-info}"
