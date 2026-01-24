# Health Checks

Rail Django includes a comprehensive health monitoring system with endpoints for Kubernetes probes, load balancers, and external monitoring systems.

## Overview

The health check extension provides:
- Multiple HTTP endpoints for liveness and readiness probes.
- Detailed component status (Database, Cache, Disk, Memory).
- A GraphQL query for system status.
- An HTML dashboard for quick visual inspection.
- Integration with Prometheus metrics and alert webhooks.

## Available Endpoints

Add the health URLs to your project's `urls.py`:

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    path("health/", include("rail_django.http.urls.health")),
]
```

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health/live/` | GET | **Liveness probe**: Checks if the process is up. Extremely lightweight. |
| `/health/ready/` | GET | **Readiness probe**: Checks if the process can handle traffic (DB, Cache). |
| `/health/` | GET | Complete status report as JSON. |
| `/health/ping/` | GET | Simple "pong" response. |
| `/health/dashboard/` | GET | HTML status dashboard (can be disabled in production). |

## Configuration

Configure the monitoring thresholds and enabled checks in your settings:

```python
RAIL_DJANGO_HEALTH = {
    "enabled": True,
    "checks": {
        "database": True,
        "cache": True,
        "disk": True,
        "memory": True,
        "external_services": True,
    },
    "thresholds": {
        "disk_usage_critical": 95,
        "memory_usage_critical": 95,
        "db_response_critical": 500, # ms
    },
    "enable_dashboard": True,
}
```

### Monitoring External Services
You can add custom HTTP checks for third-party APIs:

```python
RAIL_DJANGO_HEALTH["external_services"] = [
    {"name": "Stripe", "url": "https://api.stripe.com/v1/health"}
]
```

## GraphQL Health Query

The health status can also be queried via GraphQL:

```graphql
query HealthStatus {
  health {
    healthStatus {
      overallStatus
      timestamp
      components {
        databases { name status responseTimeMs }
        cache { status backend }
        disk { status usagePercent }
      }
    }
  }
}
```

## Kubernetes Integration

Configure your liveness and readiness probes to use the provided endpoints:

```yaml
# deployment.yaml
livenessProbe:
  httpGet:
    path: /health/live/
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready/
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

## Alerting and Metrics

### Prometheus
Rail Django can expose health metrics for Prometheus scraping:

```python
RAIL_DJANGO_HEALTH["metrics"] = {
    "enabled": True,
    "endpoint": "/metrics/",
}
```

### Webhook Alerts
Send alerts to Slack or Microsoft Teams when the health status changes:

```python
RAIL_DJANGO_HEALTH["alerting"] = {
    "enabled": True,
    "webhook_url": "https://hooks.slack.com/services/...",
}
```

## Best Practices

1. **Lightweight Liveness**: Keep `/health/live/` as fast as possible. Avoid database queries or complex logic here.
2. **Comprehensive Readiness**: Use `/health/ready/` to ensure all critical dependencies (PostgreSQL, Redis) are available before the pod starts receiving traffic.
3. **Threshold Tuning**: Adjust resource thresholds (disk, memory) based on your application's specific baseline.
4. **Security**: Restrict access to the health dashboard (`/health/dashboard/`) to internal networks or authenticated administrators in production environments.

## See Also

- [Observability](./observability.md)
- [Audit Logging](./audit-logging.md)
- [Deployment Guide](../operations/deployment.md)
