# Production Deployment

This guide covers best practices and configurations for deploying a Rail Django application to a production environment, ensuring security, performance, and reliability.

## Deployment Checklist

Before going live, ensure you have completed the following:

- [ ] **Security**: `DEBUG = False` and a strong `SECRET_KEY`.
- [ ] **GraphQL Security**: Disable introspection and GraphiQL in public environments.
- [ ] **HTTPS**: Configure SSL/TLS certificates (for example, Let's Encrypt).
- [ ] **Database**: Use a production-grade database like PostgreSQL with connection pooling.
- [ ] **Observability**: Enable Sentry and OpenTelemetry for error tracking and tracing.
- [ ] **Rate Limiting**: Enable limits to protect against brute force and DoS.
- [ ] **Static Files**: Run `collectstatic` and serve via Nginx or a CDN.

## Production Configuration

Override the default settings for your production environment:

```python
# settings/production.py

RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "enable_introspection": False, # Prevent schema discovery
        "enable_graphiql": False,      # Disable the web IDE
    },
    "performance_settings": {
        "max_query_complexity": 1000,
        "max_query_depth": 10,
    },
    "security_settings": {
        "enable_rate_limiting": True,
    }
}
```

## Infrastructure Components

### Web Server (Gunicorn/Uvicorn)
For standard GraphQL (WSGI), use Gunicorn with multiple workers:
```bash
gunicorn my_project.wsgi:application --workers 4 --threads 2 --bind 0.0.0.0:8000
```

If using **Subscriptions** (ASGI), use Uvicorn or Daphne:
```bash
uvicorn my_project.asgi:application --host 0.0.0.0 --port 8000 --workers 4
```

### Reverse Proxy (Nginx)
Always use Nginx or a similar proxy in front of your application server.

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support for Subscriptions
    location /graphql/ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### Database Optimization
Use persistent connections to improve performance:
```python
DATABASES = {
    "default": {
        "CONN_MAX_AGE": 600, # 10 minutes
    }
}
```

## Containerization (Docker)

We recommend using Docker for consistent deployments. A typical `Dockerfile` for Rail Django:

```dockerfile
FROM python:3.11-slim

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Use non-root user
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "root.wsgi:application"]
```

## Monitoring & Logs

### Health Checks
Configure your orchestrator (Kubernetes/Docker Swarm) to use the Rail Django health endpoints:
- `Liveness`: `/health/live/`
- `Readiness`: `/health/ready/`

### Error Tracking
Ensure Sentry is correctly initialized to catch unhandled exceptions in both Django and GraphQL resolvers.

## See Also

- [Complete Configuration](../core/configuration.md)
- [Health Checks](../extensions/health-checks.md)
- [Observability](../extensions/observability.md)
- [Security Guide](../security/permissions.md)
