# Manual Deployment Guide

This guide explains how to manually deploy your `rail-django` application using the provided Docker and Nginx configurations, connecting to your external database machine.

## Prerequisites

1.  **Docker & Docker Compose** installed on the application server.
2.  **External Database**: A PostgreSQL database running on a separate machine, accessible from your application server.
3.  **Domain Name / Internal DNS**: Configured to point to your VM's IP address (e.g., `app.internal.corp`).

## 1. Environment Configuration

Copy the `.env.example` file to `.env` in your project root and update the variables:

```bash
cp .env.example .env
nano .env
```

**Key variables to set:**
- `DJANGO_DEBUG=False`
- `DJANGO_SECRET_KEY`: A long, random string.
- `DATABASE_URL`: Pointing to your external machine (e.g., `postgres://user:pass@192.168.1.50:5432/my_db`).
- `DJANGO_ALLOWED_HOSTS`: Your internal domain (e.g., `app.internal.corp`) or IP.
- `DJANGO_SETTINGS_MODULE`: `root.settings.production`
- `PGHOST`, `PGUSER`, `PGPASSWORD`: Required for the automatic backup service.

## 2. Deployment Steps

Run these commands from your project root:

### A. Build and Start Services
This will build the Python image and start the Web, Nginx, and Backup containers.
```bash
docker-compose -f deploy/docker/docker-compose.yml up -d --build
```

### B. Run Migrations
Apply database schema changes to your external database:
```bash
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py migrate
```

### C. Collect Static Files
Prepare CSS, JS, and images for Nginx to serve:
```bash
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py collectstatic --no-input
```

### D. Create Superuser (Optional)
```bash
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py createsuperuser
```

## 3. Directory Structure

- **`deploy/docker/`**: Contains the Dockerfile and Compose configuration.
- **`deploy/nginx/`**: Contains the Nginx reverse proxy configuration.
- **`backups/`**: Database backups will be stored here automatically every 24h (defined in `.env`).

## 4. Maintenance

### Viewing Logs
```bash
docker-compose -f deploy/docker/docker-compose.yml logs -f
```

### Stopping the Application
```bash
docker-compose -f deploy/docker/docker-compose.yml down
```

### Updating the Application
1. Pull your latest code changes.
2. Re-run the build and migration steps:
```bash
docker-compose -f deploy/docker/docker-compose.yml up -d --build
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py migrate
```

## 5. Security Recommendations

1.  **SSL/TLS**: Mandatory. Use company-issued certificates or self-signed certs for internal traffic.
2.  **Firewall**: Configure `ufw` on your Ubuntu VM to allow traffic only from trusted internal subnets.
    ```bash
    ufw allow from 10.0.0.0/8 to any port 443
    ufw allow ssh
    ufw enable
    ```
3.  **Secrets**: Never commit your `.env` file to version control.
4.  **Updates**: Keep the VM OS updated (`apt update && apt upgrade`).

## 6. Setup HTTPS (Internal Network / Enterprise)

Since this server is inside a private company network, you cannot use standard Let's Encrypt challenges. Terminate TLS in the bundled Nginx container and mount your certificates into it.

### Step 1: Obtain Certificates
You have two options:

**Option A: Official Company Certificate (Recommended)**
Ask your IT/Security team for the SSL certificate for your internal domain (e.g., `app.corp.local`). Place the files here:
- `deploy/nginx/certs/server.crt`
- `deploy/nginx/certs/server.key`

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
Update `deploy/nginx/default.conf` and set `server_name` to your internal domain or IP. The template already redirects HTTP to HTTPS and listens on port 443.

### Step 3: Activate
```bash
docker-compose -f deploy/docker/docker-compose.yml up -d --build
```
