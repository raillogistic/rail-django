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

ENABLE_PROD_GRAPHIQL = env.bool("RAIL_ENABLE_PROD_GRAPHIQL", default=False)
ENABLE_PROD_INTROSPECTION = env.bool("RAIL_ENABLE_PROD_INTROSPECTION", default=False)

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

Use `RAIL_ENABLE_PROD_GRAPHIQL=True` and
`RAIL_ENABLE_PROD_INTROSPECTION=True` only for temporary internal debugging.
Keep both values `False` for normal production operation.

## Infrastructure Components

### Web server (ASGI default)
Use an ASGI server by default so GraphQL subscriptions and websockets work in
the same runtime:
```bash
uvicorn my_project.asgi:application --host 0.0.0.0 --port 8000 --workers 4
```

If you only need WSGI behavior, you can still run Gunicorn:
```bash
gunicorn my_project.wsgi:application --workers 4 --threads 2 --bind 0.0.0.0:8000
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

Add edge rate limits at the proxy layer so abusive traffic is rejected before it
reaches Django. The generated project template includes Nginx `limit_req`
directives for `/graphql/` and the default route. Tune the rates for your
production traffic profile.

```nginx
limit_req_zone $binary_remote_addr zone=rail_graphql_per_ip:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=rail_conn_per_ip:10m;
limit_req_status 429;

server {
    location /graphql/ {
        limit_req zone=rail_graphql_per_ip burst=40 nodelay;
        limit_conn rail_conn_per_ip 20;
        proxy_pass http://127.0.0.1:8000;
    }
}
```

If Nginx runs behind another load balancer, configure the Nginx real IP module
so `$binary_remote_addr` represents the original client and not the upstream
load balancer.

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

### Query profiling
Profile captured production GraphQL query samples before changing resolver or
index strategy. The command accepts `.graphql`, `.json`, and `.jsonl` files.

```bash
python manage.py profile_graphql_queries \
  --query-file ./logs/graphql-queries.jsonl \
  --expensive-field posts \
  --expensive-field comments
```

Use `--format json` for CI or dashboards, and `--fail-on-risk` when you want
the command to fail if it detects N+1 risk signals.

## See Also

- [Complete Configuration](../core/configuration.md)
- [Health Checks](../extensions/health-checks.md)
- [Observability](../extensions/observability.md)
- [Security Guide](../security/permissions.md)
