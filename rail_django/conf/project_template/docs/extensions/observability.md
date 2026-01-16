# Observability

## Overview

Rail Django integrates with Sentry for error tracking and OpenTelemetry for distributed tracing. This guide covers installation, configuration, and best practices for monitoring your application.

---

## Table of Contents

1. [Sentry Integration](#sentry-integration)
2. [OpenTelemetry Integration](#opentelemetry-integration)
3. [Prometheus Metrics](#prometheus-metrics)
4. [Structured Logging](#structured-logging)
5. [Advanced Configuration](#advanced-configuration)

---

## Sentry Integration

### Installation

```bash
pip install sentry-sdk
```

### Basic Configuration

```python
# root/settings/production.py
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[
        DjangoIntegration(),
    ],
    # Capture 100% of transactions for performance monitoring
    traces_sample_rate=1.0,
    # Associate users with errors
    send_default_pii=True,
)
```

### Rail Django Integration

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "error_handling": {
        "enable_sentry_integration": True,
    },
    "middleware_settings": {
        "enable_error_handling_middleware": True,
    },
}
```

### Error Monitoring

Sentry automatically captures:

- Unhandled exceptions
- GraphQL errors
- Database errors
- Authentication failures

### Traces and Breadcrumbs

```python
import sentry_sdk

# Add context
sentry_sdk.set_user({"id": user.id, "username": user.username})
sentry_sdk.set_tag("tenant", tenant_id)

# Custom breadcrumb
sentry_sdk.add_breadcrumb(
    category="graphql",
    message="Executing mutation create_order",
    level="info",
    data={"order_id": order.id},
)
```

### Custom Error Reporting

```python
from rail_django.extensions.observability import report_error

def my_resolver(root, info, **kwargs):
    try:
        # ... logic
    except CustomException as e:
        report_error(
            error=e,
            context={
                "resolver": "my_resolver",
                "user_id": info.context.user.id,
            },
            level="warning",
        )
        raise
```

---

## OpenTelemetry Integration

### Installation

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-django
pip install opentelemetry-exporter-otlp  # For OTLP export
```

### Basic Configuration

```python
# root/settings/base.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor

# Configure provider
provider = TracerProvider()
processor = BatchSpanProcessor(
    OTLPSpanExporter(endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))
)
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

# Instrument Django
DjangoInstrumentor().instrument()
```

### Rail Django Integration

```python
RAIL_DJANGO_GRAPHQL = {
    "observability_settings": {
        "enable_opentelemetry": True,
        "tracer_name": "rail_django",
        "trace_resolvers": True,
        "trace_dataloaders": True,
    },
}
```

### Distributed Tracing

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def resolve_orders(root, info, **kwargs):
    with tracer.start_as_current_span("resolve_orders") as span:
        span.set_attribute("user.id", info.context.user.id)
        span.set_attribute("filters", str(kwargs.get("filters")))

        orders = Order.objects.filter(**build_filters(kwargs))

        span.set_attribute("result.count", orders.count())
        return orders
```

### Spans and Attributes

```python
from rail_django.extensions.observability import traced

@traced(name="process_payment")
def process_payment(order, payment_data):
    """
    Automatically traced function.
    """
    # Current span receives attributes
    span = trace.get_current_span()
    span.set_attribute("order.id", order.id)
    span.set_attribute("payment.amount", payment_data["amount"])

    # ... processing logic
    return result
```

---

## Prometheus Metrics

### Installation

```bash
pip install django-prometheus
```

### Configuration

```python
# root/settings/base.py
INSTALLED_APPS += ["django_prometheus"]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    # ... other middleware
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]
```

### Custom Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Counters
graphql_requests = Counter(
    "graphql_requests_total",
    "Total GraphQL requests",
    ["operation_type", "operation_name"],
)

# Histograms
request_duration = Histogram(
    "graphql_request_duration_seconds",
    "GraphQL request duration",
    ["operation_type"],
)

# Gauges
active_connections = Gauge(
    "websocket_connections_active",
    "Active WebSocket connections",
)
```

### Middleware Usage

```python
# rail_django/extensions/observability.py
class MetricsMiddleware:
    def resolve(self, next, root, info, **kwargs):
        start_time = time.time()

        result = next(root, info, **kwargs)

        duration = time.time() - start_time
        request_duration.labels(
            operation_type=info.operation.operation.value
        ).observe(duration)

        graphql_requests.labels(
            operation_type=info.operation.operation.value,
            operation_name=info.operation.name or "anonymous",
        ).inc()

        return result
```

### Metrics Endpoint

```python
# root/urls.py
urlpatterns += [
    path("metrics/", include("django_prometheus.urls")),
]
```

Access `/metrics/` for Prometheus scraping.

---

## Structured Logging

### Configuration

```python
# root/settings/base.py
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "loggers": {
        "rail_django": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
        },
    },
}
```

### Structured Logging in Resolvers

```python
import structlog

logger = structlog.get_logger()

def resolve_create_order(root, info, input):
    logger.info(
        "Creating order",
        user_id=info.context.user.id,
        customer_id=input.customer_id,
    )

    order = Order.objects.create(**input)

    logger.info(
        "Order created",
        order_id=order.id,
        total=str(order.total),
    )

    return order
```

### Log Output

```json
{
  "timestamp": "2026-01-16T12:00:00Z",
  "level": "info",
  "logger": "myapp.resolvers",
  "message": "Order created",
  "order_id": 42,
  "total": "299.99",
  "user_id": 1,
  "request_id": "req_abc123"
}
```

---

## Advanced Configuration

### Complete Observability Setup

```python
# root/settings/production.py
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# ─── Sentry ───
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[DjangoIntegration()],
    traces_sample_rate=0.1,  # 10% sampling in prod
    profiles_sample_rate=0.1,
    environment=os.environ.get("ENVIRONMENT", "production"),
)

# ─── OpenTelemetry ───
resource = Resource.create({
    "service.name": "my-api",
    "service.version": "1.2.0",
    "deployment.environment": os.environ.get("ENVIRONMENT"),
})

provider = TracerProvider(resource=resource)
provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint=os.environ.get("OTEL_ENDPOINT"))
    )
)
trace.set_tracer_provider(provider)

# ─── Rail Django Configuration ───
RAIL_DJANGO_GRAPHQL = {
    "observability_settings": {
        "enable_sentry": True,
        "enable_opentelemetry": True,
        "enable_prometheus": True,

        # Sentry options
        "sentry_sample_rate": 0.1,
        "sentry_environment": os.environ.get("ENVIRONMENT"),

        # OpenTelemetry options
        "otel_service_name": "my-api",
        "otel_trace_resolvers": True,
        "otel_trace_db_queries": True,

        # Prometheus options
        "prometheus_labels": ["operation_type", "status"],
    },
    "error_handling": {
        "enable_sentry_integration": True,
        "enable_error_logging": True,
    },
    "middleware_settings": {
        "enable_performance_middleware": True,
        "performance_threshold_ms": 500,
    },
}
```

### Environment Variables

| Variable                      | Description                    |
| ----------------------------- | ------------------------------ |
| `SENTRY_DSN`                  | Sentry project DSN             |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint        |
| `OTEL_SERVICE_NAME`           | Service name for traces        |
| `ENVIRONMENT`                 | Environment (production, etc.) |

---

## See Also

- [Health Monitoring](./health.md) - Health endpoints
- [Audit & Logging](./audit.md) - Audit events
- [Production Deployment](../deployment/production.md) - Production configuration
