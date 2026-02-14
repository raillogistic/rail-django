# Observability extension

Rail Django provides deep insights into your GraphQL API by integrating with industry-standard observability tools like **Sentry**, **OpenTelemetry**, and **Prometheus**.

## Overview

Comprehensive monitoring is built into the framework, allowing you to track:
- GraphQL execution performance and bottlenecks.
- Error rates and detailed exception context.
- Database query performance within GraphQL operations.
- Custom metrics for business operations.

## Sentry Integration

If `sentry-sdk` is installed, Rail Django automatically captures GraphQL errors and performance traces.

### Installation
```bash
pip install sentry-sdk
```

### Configuration
```python
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

sentry_sdk.init(
    dsn="your-sentry-dsn",
    integrations=[DjangoIntegration()],
    traces_sample_rate=1.0,
)

RAIL_DJANGO_GRAPHQL = {
    "observability_settings": {
        "enable_sentry": True,
        "capture_variables": False, # Careful with PII
    },
    "error_handling": {
        "enable_sentry_integration": True,
    }
}
```

### Custom Error Reporting
You can use the provided utility to report errors with extra context:
```python
from rail_django.extensions.observability import report_error

def my_resolver(root, info, **kwargs):
    try:
        # ... logic
        pass
    except Exception as e:
        report_error(
            error=e,
            context={"resolver": "my_resolver"},
            level="warning",
        )
        raise
```

## OpenTelemetry Integration

Rail Django emits spans for GraphQL execution, validation, and field resolution when `opentelemetry-api` is present.

### Installation
```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-django
```

### Configuration
```python
RAIL_DJANGO_GRAPHQL = {
    "observability_settings": {
        "enable_opentelemetry": True,
        "trace_resolvers": True,
        "trace_dataloaders": True,
    },
}
```

### Manual Tracing
You can trace your own logic using the `traced` decorator or `trace_span` context manager:
```python
from rail_django.extensions.observability import traced, trace_span

@traced(name="complex_operation")
def my_function():
    # ... logic
    pass

def resolve_something(root, info):
    with trace_span("custom_span"):
        # ... heavy logic
        pass
```

## Prometheus Metrics

Track API health and performance using Prometheus metrics.

### Installation
```bash
pip install django-prometheus
```

### Configuration
Enable Prometheus in Rail settings:
```python
RAIL_DJANGO_GRAPHQL = {
    "observability_settings": {
        "enable_prometheus": True,
        "prometheus_labels": ["operation_type", "status"],
    },
}
```

The framework provides metrics for:
- `graphql_requests_total`: Total GraphQL requests.
- `graphql_request_duration_seconds`: Request duration histogram.
- `websocket_connections_active`: Active subscription connections.

## Structured Logging

Rail Django works best with structured logging to provide searchable, machine-readable logs.

### Configuration Example
```python
LOGGING = {
    "version": 1,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    # ... rest of Django logging config
}
```

### Logging in Resolvers
We recommend using `structlog` for rich context:
```python
import structlog
logger = structlog.get_logger()

def resolve_create_order(root, info, input):
    logger.info("Creating order", user_id=info.context.user.id)
    # ...
```

## See Also

- [Health Checks](./health-checks.md)
- [Audit Logging](./audit-logging.md)
- [Performance Optimization](../core/performance.md)
