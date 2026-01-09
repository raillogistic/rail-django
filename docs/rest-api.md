# REST API and Health Endpoints

Rail Django exposes REST endpoints for schema management, health monitoring,
exports, and templating. All endpoints return JSON unless noted.

## Schema registry endpoints

Base path: `/api/v1/`

- `GET /api/v1/schemas/` list schemas
- `POST /api/v1/schemas/` register a schema
- `GET /api/v1/schemas/<schema_name>/` schema details
- `PUT /api/v1/schemas/<schema_name>/` update schema
- `DELETE /api/v1/schemas/<schema_name>/` remove schema
- `GET /api/v1/discovery/` discovery status
- `POST /api/v1/discovery/` run auto-discovery
- `GET /api/v1/health/` registry health summary
- `GET /api/v1/metrics/` registry metrics

Example: list schemas (JWT required)

```bash
curl -s http://localhost:8000/api/v1/schemas/ \
  -H "Authorization: Bearer <jwt>"
```

Example: register a schema (admin permissions required)

```bash
curl -s -X POST http://localhost:8000/api/v1/schemas/ \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "reporting",
    "description": "Reporting schema",
    "apps": ["reports"],
    "models": [],
    "exclude_models": ["AuditEvent"],
    "settings": {
      "schema_settings": {
        "enable_graphiql": false,
        "enable_introspection": false
      }
    }
  }'
```

Note: list/detail endpoints require a JWT access token; create/update/delete,
discovery, and metrics endpoints require admin permissions. Health remains
public. Configure required permissions with
`GRAPHQL_SCHEMA_API_REQUIRED_PERMISSIONS`.

## Schema list endpoint (non-REST)

- `GET /schemas/` returns a simple list of schemas with metadata.

## Health endpoints

There are two health options:

1) Simple health URLs from `rail_django.health_urls.health_urlpatterns`:
- `/health/` dashboard (static)
- `/health/api/` status JSON
- `/health/check/`, `/health/ping/`, `/health/status/`

2) Full health views from `rail_django.views.health_views.get_health_urls()`:
- `/health/` dashboard
- `/health/api/` detailed JSON
- `/health/metrics/`, `/health/components/`, `/health/history/`

Include the desired URL patterns in your project `urls.py`.

## Export endpoint

Path: `POST /api/v1/export/`

Requires a JWT in the `Authorization` header.

```bash
curl -s -X POST http://localhost:8000/api/v1/export/ \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "blog",
    "model_name": "Post",
    "file_extension": "csv",
    "filename": "posts",
    "fields": ["title", "author.username", {"accessor": "slug", "title": "Slug"}],
    "ordering": ["-created_at"],
    "max_rows": 10000,
    "variables": {
      "status__exact": "published"
    }
  }'
```

Notes:

- Exports enforce `RAIL_DJANGO_EXPORT` settings for allowlists, row limits,
  and rate limiting.
- CSV responses may stream when `stream_csv` is enabled.

## PDF templating endpoints

Path: `/api/templates/<template_path>/<pk>/`

Templates are registered with `@model_pdf_template`. The endpoint returns a
PDF file (content-type `application/pdf`). Use JWT auth if enabled.

Example:

```bash
curl -s -H "Authorization: Bearer <jwt>" \
  http://localhost:8000/api/templates/orders/printable/detail/123/
```
