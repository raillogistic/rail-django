#!/bin/sh
set -e

echo "running container"
cd /home/app

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-root.settings.production}"

# python manage.py flush --no-input
python manage.py collectstatic --noinput
python manage.py migrate
exec gunicorn root.asgi:application \
    --bind 0.0.0.0:8000 \
    --worker-class uvicorn_worker.UvicornWorker \
    --workers "${WEB_CONCURRENCY:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}"
