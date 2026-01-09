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

Since this server is inside a private company network, you cannot use standard Let's Encrypt challenges. You should use **Host Nginx** to handle SSL using certificates provided by your IT department.

### Step 1: Adjust Docker Configuration
Move the Docker container to a private port so the Host Nginx can take over port 80/443.

1. Open `deploy/docker/docker-compose.yml`.
2. Change the `nginx` service ports:
   ```yaml
   nginx:
     # ...
     ports:
       - "127.0.0.1:8080:80"  # Bind to localhost port 8080
   ```
3. Restart your containers:
   ```bash
docker-compose -f deploy/docker/docker-compose.yml up -d --build
```

### Step 2: Obtain Certificates
You have two options:

**Option A: Official Company Certificate (Recommended)**
Ask your IT/Security team for the SSL certificate for your internal domain (e.g., `app.corp.local`).
You need two files:
- `your_domain.crt` (The public certificate)
- `your_domain.key` (The private key)

**Option B: Self-Signed Certificate (For Testing)**
If you don't have an official cert, generate a self-signed one:
```bash
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/selfsigned.key \
  -out /etc/ssl/certs/selfsigned.crt
```

### Step 3: Configure Host Nginx
Install Nginx on the VM:
```bash
sudo apt update
sudo apt install nginx
```

Create a secure configuration file:
```bash
sudo nano /etc/nginx/sites-available/my_internal_app
```

Paste this configuration (adjust paths and domain):

```nginx
server {
    listen 80;
    server_name app.internal.corp; # Your internal domain or IP
    return 301 https://$host$request_uri; # Force HTTPS
}

server {
    listen 443 ssl;
    server_name app.internal.corp;

    # Point to your certificates
    ssl_certificate /etc/ssl/certs/your_domain.crt;      # Or selfsigned.crt
    ssl_certificate_key /etc/ssl/private/your_domain.key; # Or selfsigned.key

    # SSL Settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://127.0.0.1:8080; # Points to Docker Container
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Step 4: Activate
```bash
sudo ln -s /etc/nginx/sites-available/my_internal_app /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```
