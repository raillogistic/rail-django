#!/bin/sh

# Wait for database
if [ "$DATABASE_URL" ]; then
    echo "Waiting for database..."
    
    # Extract host and port from DATABASE_URL
    # Assumes format postgres://user:pass@host:port/dbname
    # Simple parsing - for production might need something more robust
    DB_HOST=$(echo $DATABASE_URL | sed -r 's/.*@([^:]+):.*/\1/')
    DB_PORT=$(echo $DATABASE_URL | sed -r 's/.*:([0-9]+)\/.*/\1/')
    
    while ! nc -z $DB_HOST $DB_PORT; do
      sleep 0.1
    done
    
    echo "Database started"
fi

echo "Running migrations..."
python manage.py migrate

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting server..."
# Optimization:
# - workers: Automatic based on CPU (usually 2*cores + 1) or configurable
# - threads: 4 threads per worker handles I/O waiting better than sync workers
# - preload: Loads code once before forking, saving RAM and starting faster
# - worker-class: gthread enables threading
WORKERS=${GUNICORN_WORKERS:-3}
THREADS=${GUNICORN_THREADS:-4}

exec gunicorn {{ project_name }}.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers $WORKERS \
    --threads $THREADS \
    --worker-class gthread \
    --preload