# Observability

Rail Django integrates with **Sentry** and **OpenTelemetry** to provide deep insights into your GraphQL API.

## Sentry Integration

If `sentry-sdk` is installed, Rail Django automatically captures:
*   GraphQL Errors (as exceptions).
*   Performance Traces (resolvers, DB queries).

### Configuration

```python
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

sentry_sdk.init(
    dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
    integrations=[DjangoIntegration()],
    # Enable performance monitoring
    traces_sample_rate=1.0, 
)

RAIL_DJANGO_GRAPHQL = {
    "observability_settings": {
        "enable_sentry": True,
        "capture_variables": False, # careful with PII
    }
}
```

## OpenTelemetry

If `opentelemetry-api` is installed, the framework emits spans for:
*   GraphQL Execution (`graphql.execute`)
*   Validation (`graphql.validate`)
*   Field Resolution (`graphql.resolve`)

### Setup

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-django
```

Rail Django will automatically detect the library and start creating child spans for your GraphQL operations within the Django request trace.

### Custom Tracing

You can trace your own resolvers using the provided utility.

```python
from rail_django.extensions.observability import trace_span

def resolve_complex_calculation(root, info):
    with trace_span("complex_calculation"):
        # ... heavy logic ...
        pass
```
