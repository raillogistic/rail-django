# Production Deployment

## Overview

This guide covers deploying a Rail Django application in production, including Docker configuration, environment variables, deployment checklist, and best practices.

---

## Table of Contents

1. [Docker Configuration](#docker-configuration)
2. [Environment Variables](#environment-variables)
3. [Production Checklist](#production-checklist)
4. [Manual Deployment](#manual-deployment)
5. [HTTPS and Certificates](#https-and-certificates)
6. [Maintenance Procedures](#maintenance-procedures)
7. [Troubleshooting](#troubleshooting)
8. [Network Security](#network-security)

---

## Docker Configuration

### Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# Python dependencies
COPY requirements/prod.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Non-root user for security
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

# Gunicorn entrypoint
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "root.wsgi:application"]

EXPOSE 8000
```

### Docker Compose

```yaml
# docker-compose.yml
version: "3.8"

services:
  web:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env.production
    depends_on:
      - db
      - redis
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/ping/"]
      interval: 30s
      timeout: 10s
      retries: 3

  db:
    image: postgres:15-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./deploy/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./staticfiles:/app/static:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - web
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

### Nginx Configuration

```nginx
# deploy/nginx.conf
events {
    worker_connections 1024;
}

http {
    include mime.types;
    default_type application/octet-stream;

    # Logging
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;

    # Upstream
    upstream django {
        server web:8000;
    }

    # HTTP to HTTPS redirect
    server {
        listen 80;
        server_name example.com;
        return 301 https://$server_name$request_uri;
    }

    # HTTPS
    server {
        listen 443 ssl http2;
        server_name example.com;

        ssl_certificate /etc/nginx/certs/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/privkey.pem;

        # SSL configuration
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
        ssl_prefer_server_ciphers on;

        # Security headers
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;
        add_header X-XSS-Protection "1; mode=block";

        # Static files
        location /static/ {
            alias /app/static/;
            expires 30d;
        }

        # GraphQL
        location /graphql/ {
            proxy_pass http://django;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # WebSocket support
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }

        # API
        location / {
            proxy_pass http://django;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

---

## Environment Variables

### .env.production Example

```bash
# Django
DJANGO_SETTINGS_MODULE=root.settings.production
DJANGO_SECRET_KEY=your-very-long-and-secure-secret-key
DEBUG=False
ALLOWED_HOSTS=example.com,www.example.com

# Database
DATABASE_URL=postgres://user:password@db:5432/dbname

# Redis
REDIS_URL=redis://redis:6379/0

# JWT
JWT_SECRET_KEY=your-jwt-secret-key
JWT_ACCESS_TOKEN_LIFETIME=30
JWT_REFRESH_TOKEN_LIFETIME=10080

# Email
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=noreply@example.com
EMAIL_HOST_PASSWORD=your-email-password
EMAIL_USE_TLS=True

# Sentry (optional)
SENTRY_DSN=https://xxx@sentry.io/xxx

# Storage (optional)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_STORAGE_BUCKET_NAME=your-bucket

# Security
CORS_ALLOWED_ORIGINS=https://example.com,https://www.example.com
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
```

---

## Production Checklist

### Security

- [ ] `DEBUG=False`
- [ ] Strong unique `DJANGO_SECRET_KEY`
- [ ] `ALLOWED_HOSTS` correctly configured
- [ ] HTTPS enabled with valid certificate
- [ ] `CSRF_TRUSTED_ORIGINS` configured
- [ ] `CORS_ALLOWED_ORIGINS` configured
- [ ] GraphQL introspection disabled (optional)
- [ ] Rate limiting enabled
- [ ] Secure cookies configured

### Database

- [ ] PostgreSQL (not SQLite)
- [ ] Regular backups configured
- [ ] User with limited privileges
- [ ] SSL connections if remote

### Performance

- [ ] `collectstatic` executed
- [ ] Gunicorn with multiple workers
- [ ] Redis for cache and rate limiting
- [ ] CDN for static files (optional)

### Monitoring

- [ ] Health checks configured
- [ ] Sentry or equivalent for error tracking
- [ ] Prometheus metrics (optional)
- [ ] Centralized logs

### Backup

- [ ] Automatic daily backups
- [ ] Tested restore procedure
- [ ] Off-site backup storage

---

## Manual Deployment

### Step 1: Prepare the Server

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.11 python3.11-venv postgresql nginx redis-server

# Create application user
sudo useradd -m -s /bin/bash appuser
```

### Step 2: Configure Database

```bash
# Create database and user
sudo -u postgres psql
CREATE DATABASE myproject;
CREATE USER myproject WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE myproject TO myproject;
\q
```

### Step 3: Deploy Application

```bash
# Clone repository
cd /var/www
sudo git clone https://github.com/your/repo.git myproject
sudo chown -R appuser:appuser myproject

# Create virtual environment
sudo -u appuser bash
cd /var/www/myproject
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements/prod.txt

# Configure environment
cp .env.example .env
nano .env  # Edit values

# Initialize
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

### Step 4: Configure Systemd

```ini
# /etc/systemd/system/myproject.service
[Unit]
Description=My Project Gunicorn Service
After=network.target

[Service]
User=appuser
Group=appuser
WorkingDirectory=/var/www/myproject
Environment="PATH=/var/www/myproject/venv/bin"
EnvironmentFile=/var/www/myproject/.env
ExecStart=/var/www/myproject/venv/bin/gunicorn \
    --workers 4 \
    --bind unix:/var/www/myproject/gunicorn.sock \
    root.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable myproject
sudo systemctl start myproject
```

---

## HTTPS and Certificates

### Let's Encrypt with Certbot

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d example.com -d www.example.com

# Automatic renewal
sudo crontab -e
# Add:
0 0 1 * * /usr/bin/certbot renew --quiet
```

---

## Maintenance Procedures

### Update Application

```bash
cd /var/www/myproject
git pull origin main
source venv/bin/activate
pip install -r requirements/prod.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart myproject
```

### Database Backup

```bash
# Manual backup
pg_dump -U myproject myproject > backup_$(date +%Y%m%d).sql

# Automatic backup (crontab)
0 2 * * * pg_dump -U myproject myproject > /backups/daily/backup_$(date +\%Y\%m\%d).sql
```

### Log Management

```bash
# View logs
sudo journalctl -u myproject -f

# Rotate logs
sudo logrotate /etc/logrotate.d/myproject
```

---

## Troubleshooting

### Application Not Starting

```bash
# Check status
sudo systemctl status myproject

# View detailed logs
sudo journalctl -u myproject -n 100

# Check configuration
python manage.py check --deploy
```

### Database Connection Issues

```bash
# Test connection
python manage.py dbshell

# Check PostgreSQL status
sudo systemctl status postgresql
```

### 502 Bad Gateway

```bash
# Check if Gunicorn is running
sudo systemctl status myproject

# Check socket permissions
ls -la /var/www/myproject/gunicorn.sock

# Check Nginx configuration
sudo nginx -t
```

### High Memory Usage

```bash
# Check processes
ps aux | grep gunicorn

# Adjust workers
# In gunicorn config:
--workers 2 --threads 4 --worker-class gthread
```

---

## Network Security

### Firewall (UFW)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow http
sudo ufw allow https
sudo ufw enable
```

### Fail2Ban

```bash
sudo apt install fail2ban
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo nano /etc/fail2ban/jail.local
# Enable [sshd] and [nginx-http-auth]
sudo systemctl restart fail2ban
```

### Database Security

```bash
# Limit PostgreSQL connections
# In /etc/postgresql/15/main/pg_hba.conf
local   all   all                 peer
host    all   all   127.0.0.1/32  scram-sha-256
host    all   all   ::1/128       scram-sha-256
# Deny external connections
```

---

## See Also

- [Configuration](../graphql/configuration.md) - All settings
- [Health Monitoring](../extensions/health.md) - Health endpoints
- [Observability](../extensions/observability.md) - Sentry and metrics
