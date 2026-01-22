# Deployment Guide

This guide covers best practices for deploying Rail Django applications to production.

## Checklist

1.  [ ] **Disable Introspection**: In `RAIL_DJANGO_GRAPHQL` settings.
2.  [ ] **Disable GraphiQL**: Prevent public access to the IDE.
3.  [ ] **Enable Observability**: Configure Sentry/OpenTelemetry.
4.  [ ] **Optimize Database**: Ensure `conn_max_age` is set.
5.  [ ] **Secure Headers**: Ensure `ALLOWED_HOSTS` and CORS settings are tight.

## Configuration for Production

```python
# settings.py

DEBUG = False

RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "enable_introspection": False, # IMPORTANT
        "enable_graphiql": False,
    },
    "performance_settings": {
        "enable_query_cost_analysis": True,
        "max_query_complexity": 2000,
    },
    "security_settings": {
        "enable_rate_limiting": True,
    }
}
```

## Database Connection Pooling

GraphQL often generates many small queries. Use persistent connections.

```python
DATABASES = {
    "default": {
        # ...
        "CONN_MAX_AGE": 600, # 10 minutes
    }
}
```

## Gunicorn / Uvicorn

If you are using Subscriptions, you must use an ASGI server like `uvicorn` or `daphne`.

```bash
uvicorn my_project.asgi:application --host 0.0.0.0 --port 8000 --workers 4
```

If you are only using Queries/Mutations (WSGI), `gunicorn` is sufficient.

```bash
gunicorn my_project.wsgi:application --workers 4 --threads 4
```

### Sample `gunicorn.conf.py`

```python
workers = 4
threads = 2
bind = "0.0.0.0:8000"
timeout = 30
max_requests = 1000
worker_class = "gthread"
```

### Sample Nginx Config

```nginx
server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # If using subscriptions (WebSockets)
    location /graphql/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## Caching

Enable query caching to reduce DB load for hot queries.

```python
RAIL_DJANGO_GRAPHQL = {
    "performance_settings": {
        "enable_query_caching": True,
        "query_cache_timeout": 60,
    }
}
```