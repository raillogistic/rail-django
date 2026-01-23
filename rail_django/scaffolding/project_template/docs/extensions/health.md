# Health Monitoring

## Overview

Rail Django includes health monitoring endpoints for integration with Kubernetes, load balancers, and monitoring systems. This guide covers configuration, available checks, and best practices.

---

## Table of Contents

1. [Available Endpoints](#available-endpoints)
2. [Configuration](#configuration)
3. [GraphQL Query](#graphql-query)
4. [Checked Components](#checked-components)
5. [HTML Dashboard](#html-dashboard)
6. [Kubernetes Integration](#kubernetes-integration)
7. [Alerting](#alerting)
8. [Best Practices](#best-practices)

---

## Available Endpoints

| Endpoint             | Method | Description            |
| -------------------- | ------ | ---------------------- |
| `/health/`           | GET    | Complete status (JSON) |
| `/health/ping/`      | GET    | Simple ping (text)     |
| `/health/ready/`     | GET    | Readiness check        |
| `/health/live/`      | GET    | Liveness check         |
| `/health/dashboard/` | GET    | HTML dashboard         |

### /health/ping/

```bash
curl http://localhost:8000/health/ping/
# Response: pong
```

### /health/

```json
{
  "status": "healthy",
  "timestamp": "2026-01-16T12:00:00Z",
  "version": "1.2.0",
  "components": {
    "database": {
      "status": "healthy",
      "response_time_ms": 5
    },
    "cache": {
      "status": "healthy",
      "response_time_ms": 2
    },
    "disk": {
      "status": "healthy",
      "usage_percent": 45
    },
    "memory": {
      "status": "healthy",
      "usage_percent": 62
    }
  }
}
```

---

## Configuration

### Basic Configuration

```python
# root/settings/base.py
RAIL_DJANGO_HEALTH = {
    # Activation
    "enabled": True,

    # Available checks
    "checks": {
        "database": True,
        "cache": True,
        "disk": True,
        "memory": True,
        "external_services": True,
    },

    # Thresholds
    "thresholds": {
        "disk_usage_warning": 80,  # %
        "disk_usage_critical": 95,
        "memory_usage_warning": 80,
        "memory_usage_critical": 95,
        "db_response_warning": 100,  # ms
        "db_response_critical": 500,
    },

    # Security
    "require_authentication": False,
    "allowed_ips": None,  # None = all

    # Dashboard
    "enable_dashboard": True,
}
```

---

## GraphQL Query

### Health Query

```graphql
query HealthStatus {
  health {
    healthStatus {
      overallStatus
      timestamp
      version
      components {
        databases {
          name
          status
          responseTimeMs
          error
        }
        cache {
          status
          backend
          responseTimeMs
        }
        disk {
          status
          usagePercent
          freeGb
        }
        memory {
          status
          usagePercent
          availableMb
        }
        externalServices {
          name
          status
          responseTimeMs
          error
        }
      }
    }
  }
}
```

### Response

```json
{
  "data": {
    "health": {
      "healthStatus": {
        "overallStatus": "healthy",
        "timestamp": "2026-01-16T12:00:00Z",
        "version": "1.2.0",
        "components": {
          "databases": [
            {
              "name": "default",
              "status": "healthy",
              "responseTimeMs": 5,
              "error": null
            }
          ],
          "cache": {
            "status": "healthy",
            "backend": "redis",
            "responseTimeMs": 2
          },
          "disk": {
            "status": "warning",
            "usagePercent": 82,
            "freeGb": 18.5
          },
          "memory": {
            "status": "healthy",
            "usagePercent": 62,
            "availableMb": 3800
          },
          "externalServices": []
        }
      }
    }
  }
}
```

---

## Checked Components

### Database

Checks connectivity and response time for all configured databases.

```python
DATABASES = {
    "default": { ... },
    "replica": { ... },
}
```

All databases are checked, and their individual status is reported.

### Cache

Checks Redis or configured cache backend.

```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://localhost:6379/0",
    },
}
```

### Disk

Checks available disk space on configured paths.

```python
RAIL_DJANGO_HEALTH = {
    "disk_paths": ["/", "/var/data"],
}
```

### Memory

Checks system memory usage.

### External Services

Checks connectivity to external services.

```python
RAIL_DJANGO_HEALTH = {
    "external_services": [
        {
            "name": "Payment Gateway",
            "url": "https://api.stripe.com/v1/health",
            "timeout": 5,
            "expected_status": 200,
        },
        {
            "name": "Email Service",
            "url": "https://api.sendgrid.com/v3/health",
            "timeout": 5,
        },
    ],
}
```

---

## HTML Dashboard

Access `/health/dashboard/` for a visual dashboard.

### Features

- Real-time status display
- Historical graphs (if metrics enabled)
- Component details
- Auto-refresh

### Configuration

```python
RAIL_DJANGO_HEALTH = {
    "enable_dashboard": True,
    "dashboard_refresh_seconds": 30,
    "dashboard_require_auth": True,
}
```

---

## Kubernetes Integration

### Liveness Probe

Checks if the application is running and responsive.

```yaml
# deployment.yaml
livenessProbe:
  httpGet:
    path: /health/live/
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

### Readiness Probe

Checks if the application is ready to receive traffic.

```yaml
readinessProbe:
  httpGet:
    path: /health/ready/
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3
```

### Startup Probe

Checks if the application has started successfully.

```yaml
startupProbe:
  httpGet:
    path: /health/ping/
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
  failureThreshold: 30
```

---

## Alerting

### Webhook Alerts

```python
RAIL_DJANGO_HEALTH = {
    "alerting": {
        "enabled": True,
        "webhook_url": "https://hooks.slack.com/services/xxx",
        "alert_on": ["critical", "warning"],
        "cooldown_minutes": 15,  # Avoid alert flood
    },
}
```

### Custom Alert Handler

```python
# myapp/health.py
def custom_alert_handler(status, components):
    """
    Custom alert handler.

    Args:
        status: Overall status (healthy, warning, critical).
        components: Component details.
    """
    if status == "critical":
        send_pagerduty_alert(components)
    elif status == "warning":
        send_slack_notification(components)

RAIL_DJANGO_HEALTH = {
    "alert_callback": "myapp.health.custom_alert_handler",
}
```

### Prometheus Metrics

```python
RAIL_DJANGO_HEALTH = {
    "metrics": {
        "enabled": True,
        "endpoint": "/metrics/",
        "backend": "prometheus",
    },
}
```

Exposed metrics:

```
# HELP app_health_status Application health status
# TYPE app_health_status gauge
app_health_status{component="database"} 1
app_health_status{component="cache"} 1
app_health_status{component="disk"} 0.5
app_health_status{component="memory"} 1

# HELP app_db_response_time_ms Database response time
# TYPE app_db_response_time_ms gauge
app_db_response_time_ms{database="default"} 5.2
```

---

## Best Practices

### 1. Differentiate Liveness and Readiness

```python
# Liveness: simple check, always responds
# /health/live/ -> only checks if app is running

# Readiness: complete check
# /health/ready/ -> checks DB, cache, dependencies
```

### 2. Set Appropriate Thresholds

```python
RAIL_DJANGO_HEALTH = {
    "thresholds": {
        "disk_usage_warning": 80,
        "disk_usage_critical": 95,
    },
}
```

### 3. Don't Block Health Checks

```python
# ❌ Avoid heavy operations in health checks
# ✅ Keep checks lightweight and fast
```

### 4. Monitor Health Endpoint Response Time

```python
# Alert if health check takes too long
RAIL_DJANGO_HEALTH = {
    "check_timeout_ms": 5000,
    "alert_on_slow_checks": True,
}
```

### 5. Secure the Dashboard

```python
RAIL_DJANGO_HEALTH = {
    "dashboard_require_auth": True,
    "dashboard_allowed_roles": ["admin", "ops"],
}
```

### 6. Test Health Checks

```python
from django.test import TestCase

class HealthCheckTests(TestCase):
    def test_ping(self):
        response = self.client.get("/health/ping/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "pong")

    def test_health_status(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
```

---

## See Also

- [Observability](./observability.md) - Sentry and metrics
- [Production Deployment](../deployment/production.md) - Kubernetes configuration
- [Configuration](../graphql/configuration.md) - All settings
