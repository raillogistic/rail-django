# Health checks

Rail Django provides public process and dependency probes plus protected
diagnostic views.

## URL configuration

The framework URL configuration already includes these routes. A custom root
URL configuration can include them directly:

```python
from rail_django.http.urls.health import health_urlpatterns

urlpatterns += health_urlpatterns
```

## Endpoints

| Endpoint | Access | Purpose |
| --- | --- | --- |
| `/health/live/` | Public | Dependency-free process liveness probe. |
| `/health/ready/` | Public | Readiness report for configured dependencies. |
| `/health/check/` | Public | Alias of the readiness report. |
| `/health/` | Staff | HTML diagnostics dashboard. |
| `/health/api/` | Staff | Detailed health data in JSON. |
| `/health/metrics/` | Staff | Current process metrics. |
| `/health/components/` | Staff | Detailed component status. |
| `/health/history/` | Staff | Returns `501` until an application supplies persistent history storage. |

Detailed endpoints return `401` for anonymous requests and `403` for
authenticated non-staff users. Set `HEALTH_DIAGNOSTICS_PUBLIC = True` only
when a trusted network layer already protects them.

`HEALTH_CHECK_CACHE_TTL_SECONDS` controls readiness-report caching.
`HEALTH_REFRESH_INTERVAL` and `HEALTH_AUTO_REFRESH` configure the dashboard.

## Kubernetes example

```yaml
livenessProbe:
  httpGet:
    path: /health/live/
    port: 8000

readinessProbe:
  httpGet:
    path: /health/ready/
    port: 8000
```

Keep the liveness probe dependency-free. Use readiness to prevent traffic from
reaching a process whose required services are unavailable.
