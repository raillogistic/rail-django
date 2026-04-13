# Manual Deployment Guide

This guide explains how to manually deploy your `rail-django` application using the provided Docker and Nginx configurations, connecting to your external database machine.

## Prerequisites

1.  **Docker & Docker Compose** installed on the application server.
2.  **External Database**: A PostgreSQL database running on a separate machine, accessible from your application server.
3.  **Domain Name / Internal DNS**: Configured to point to your VM's IP address (e.g., `app.internal.corp`).

## 1. Environment Configuration

Use `.env.prod` for deployment in your project root and update the variables:

```bash
nano .env.prod
```

**Key variables to set:**
- `DJANGO_DEBUG=False`
- `DJANGO_SECRET_KEY`: A long, random string.
- `DATABASE_URL`: Pointing to your external machine (e.g., `postgres://user:pass@192.168.1.50:5432/my_db`). Also used by deploy/backup.sh.
- `DJANGO_ALLOWED_HOSTS`: Your internal domain (e.g., `app.internal.corp`) or IP.
- `DJANGO_SETTINGS_MODULE`: `root.settings.production`
- `LOG_PATH`: Host path for log files (absolute or relative to `deploy/docker/`).
- `RAIL_ENABLE_PROD_GRAPHIQL=False`: Keep GraphiQL disabled by default in production.
- `RAIL_ENABLE_PROD_INTROSPECTION=False`: Keep introspection disabled by default in production.
The deploy script auto-generates `DJANGO_SECRET_KEY` when it is missing or a
placeholder value. It still rejects placeholder values for
`DJANGO_SUPERUSER_PASSWORD`.

**Optional runtime toggles:**
- `RUN_MIGRATIONS` / `RUN_COLLECTSTATIC`: The bundled `web` service enables
  these at container startup, so the app runs `migrate` and
  `collectstatic` before the server starts.
- `DJANGO_CHECK_DEPLOY`: Run `python manage.py check --deploy` on container start.
- `MEDIA_PATH`: Host path for uploads (absolute or relative to `deploy/docker/`).

**Runtime server defaults (ASGI):**
- `DJANGO_SERVER_MODE=asgi`
- `DJANGO_ASGI_MODULE=root.asgi:application`
- `ASGI_BIND=0.0.0.0`
- `ASGI_PORT=8000`

**Optional WSGI fallback (Gunicorn):**
- Set `DJANGO_SERVER_MODE=wsgi`
- `GUNICORN_WORKERS`, `GUNICORN_THREADS`
- `GUNICORN_TIMEOUT`, `GUNICORN_GRACEFUL_TIMEOUT`, `GUNICORN_KEEPALIVE`
- `GUNICORN_MAX_REQUESTS`, `GUNICORN_MAX_REQUESTS_JITTER`
- `GUNICORN_LOG_LEVEL`, `GUNICORN_ACCESS_LOG`, `GUNICORN_ERROR_LOG`

## 2. One-Click Deployment (Recommended)

From your project root:

```bash
bash deploy/deploy.sh
```

The script validates `.env.prod`, ensures TLS certs exist, validates the
Nginx config, builds the images, and starts the containers. The `web`
container now owns `migrate` and `collectstatic` during its startup sequence.

### Optional Flags
```bash
bash deploy/deploy.sh --follow-logs
```

### Superuser automation
Set these in your `.env.prod` and re-run the script:
```bash
DEPLOY_CREATE_SUPERUSER=1
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=<strong-random-password>
```

### CI Example (Non-Interactive)
In your CI job, export secrets as environment variables, then template `.env.prod` and deploy:
```bash
cat > .env.prod <<EOF
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
DJANGO_SETTINGS_MODULE=root.settings.production
DATABASE_URL=${DATABASE_URL}
DJANGO_ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS}

DEPLOY_CREATE_SUPERUSER=1
DJANGO_SUPERUSER_USERNAME=${DJANGO_SUPERUSER_USERNAME}
DJANGO_SUPERUSER_EMAIL=${DJANGO_SUPERUSER_EMAIL}
DJANGO_SUPERUSER_PASSWORD=${DJANGO_SUPERUSER_PASSWORD}
EOF

bash deploy/deploy.sh
```

## 3. Manual Deployment Steps

Run these commands from your project root:

### A. Build web and nginx images
Build the Python and Nginx images before starting the stack:
```bash
docker-compose -f deploy/docker/docker-compose.yml build web nginx
```
The default web runtime is ASGI, so GraphQL subscriptions are available without
extra runtime changes.

### B. Validate the Nginx configuration
Validate the rendered Nginx config before you start the stack:
```bash
docker-compose -f deploy/docker/docker-compose.yml run --rm --no-deps --entrypoint nginx nginx -t
```

### C. Run schema tasks
Run migrations and collect static files before the services start:
```bash
docker-compose -f deploy/docker/docker-compose.yml run --rm --entrypoint python web manage.py migrate
docker-compose -f deploy/docker/docker-compose.yml run --rm --entrypoint python web manage.py collectstatic --no-input
```

### D. Start services
Start the Web and Nginx containers after schema tasks complete:
```bash
docker-compose -f deploy/docker/docker-compose.yml up -d
```

## 4. Directory Structure

- **`deploy/docker/`**: Contains the Dockerfile and Compose configuration.
- **`deploy/nginx/`**: Contains the Nginx reverse proxy configuration.
- **`backups/`**: Database backups are written here by `deploy/backup.sh`.

## 5. Maintenance

### Viewing Logs
```bash
docker-compose -f deploy/docker/docker-compose.yml logs -f
```
Log files are also written to `/home/app/web/logs` inside the container. If you
set `LOG_PATH`, read them directly on the host.

### Health Endpoints
Use these endpoints for orchestrator probes and diagnostics:
- Liveness: `/health/live/` (alias of `/health/check/`)
- Readiness: `/health/ready/` (alias of `/health/check/`)
- Detailed diagnostics (`/health/api/`, `/health/metrics/`,
  `/health/components/`, `/health/history/`) are restricted to loopback callers
  by the scaffolded Nginx config.

The bundled Docker healthcheck calls the readiness endpoint over plain HTTP on
the internal app port and sends `X-Forwarded-Proto: https`. Keep that header in
place when `SECURE_SSL_REDIRECT` is enabled, or Django will redirect the probe
to HTTPS and Docker will keep the `web` service in an unhealthy state.

### Stopping the Application
```bash
docker-compose -f deploy/docker/docker-compose.yml down
```

### Updating the Application
1. Pull your latest code changes.
2. Rebuild images, validate Nginx, and restart the stack:
```bash
docker-compose -f deploy/docker/docker-compose.yml build web nginx
docker-compose -f deploy/docker/docker-compose.yml run --rm --no-deps --entrypoint nginx nginx -t
docker-compose -f deploy/docker/docker-compose.yml up -d
```

### Running Backups
Run a one-shot backup on the host:

```bash
bash deploy/backup.sh
```

To automate backups, schedule this command with cron/systemd on your server.

### Production GraphiQL policy
GraphiQL and introspection are disabled by default in production templates.
If you need temporary internal access, set:

```bash
RAIL_ENABLE_PROD_GRAPHIQL=True
RAIL_ENABLE_PROD_INTROSPECTION=True
```

GraphiQL remains restricted to superusers from loopback hosts.

## 6. Security Recommendations

1.  **SSL/TLS**: Mandatory. Use company-issued certificates or self-signed certs for internal traffic.
2.  **Firewall**: Configure `ufw` on your Ubuntu VM to allow traffic only from trusted internal subnets.
    ```bash
    ufw allow from 10.0.0.0/8 to any port 8000
    ufw allow ssh
    ufw enable
    ```
3.  **Secrets**: Never commit your `.env.dev` or `.env.prod` files, TLS private keys, or TLS certificates to version control.
4.  **Updates**: Keep the VM OS updated (`apt update && apt upgrade`).

## 7. Setup HTTPS (Internal Network / Enterprise)

Since this server is inside a private company network, you cannot use standard Let's Encrypt challenges. Terminate TLS in the bundled Nginx container and bake your certificates into the scaffolded Nginx image.

### Step 1: Obtain Certificates
You have two options:

**Option A: Official Company Certificate (Recommended)**
Ask your IT/Security team for the SSL certificate for your internal domain (e.g., `app.corp.local`). Place the files here:
- `deploy/nginx/certs/server.crt`
- `deploy/nginx/certs/server.key`
If any previous key material was committed or shared, rotate it immediately and
treat prior copies as compromised.

**Option B: Self-Signed Certificate (For Testing)**
If you don't have an official cert, generate a self-signed one:
```bash
mkdir -p deploy/nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout deploy/nginx/certs/server.key \
  -out deploy/nginx/certs/server.crt \
  -subj "/CN=app.internal.corp"
```

### Step 2: Configure Nginx
Update `deploy/nginx/default.conf` and set `server_name` to your internal domain or IP. The template serves HTTPS directly on port 8000.

### Step 3: Activate
```bash
docker-compose -f deploy/docker/docker-compose.yml up -d --build
```

When certificates or `deploy/nginx/default.conf` change, rebuild Nginx:
```bash
docker-compose -f deploy/docker/docker-compose.yml build nginx
docker-compose -f deploy/docker/docker-compose.yml up -d
```


