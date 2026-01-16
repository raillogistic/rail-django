# Observabilité (Sentry & OpenTelemetry)

## Vue d'Ensemble

Rail Django s'intègre avec les principales plateformes d'observabilité pour le monitoring des erreurs, le tracing distribué et les métriques de performance. Ce guide couvre l'intégration avec Sentry et OpenTelemetry.

---

## Table des Matières

1. [Sentry](#sentry)
2. [OpenTelemetry](#opentelemetry)
3. [Métriques Prometheus](#métriques-prometheus)
4. [Logging Structuré](#logging-structuré)
5. [Configuration Avancée](#configuration-avancée)

---

## Sentry

### Installation

```bash
pip install sentry-sdk
```

### Configuration Basique

```python
# root/settings/base.py
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.graphene import GrapheneIntegration

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[
        DjangoIntegration(),
        GrapheneIntegration(),
    ],
    # Taux d'échantillonnage des traces
    traces_sample_rate=0.1,  # 10% en production
    # Environnement
    environment=os.environ.get("DJANGO_ENV", "development"),
    # Release (optionnel)
    release=os.environ.get("APP_VERSION"),
    # Envoyer les PII (false en prod par défaut)
    send_default_pii=False,
)
```

### Configuration Rail Django

```python
RAIL_DJANGO_GRAPHQL = {
    "error_handling": {
        "enable_sentry_integration": True,
    },
    "monitoring_settings": {
        "sentry_dsn": os.environ.get("SENTRY_DSN"),
        "sentry_traces_sample_rate": 0.1,
        "sentry_profiles_sample_rate": 0.1,
    },
}
```

### Enrichissement des Erreurs

Rail Django ajoute automatiquement du contexte aux erreurs Sentry :

```python
# Contexte ajouté automatiquement
{
    "user": {
        "id": user.id,
        "username": user.username,
        "email": user.email,
    },
    "graphql": {
        "operation_name": "CreateOrder",
        "operation_type": "mutation",
        "variables": {...},  # Variables non sensibles
    },
    "request": {
        "ip_address": "...",
        "user_agent": "...",
    },
}
```

### Breadcrumbs

Les opérations GraphQL sont enregistrées comme breadcrumbs :

```python
# Exemple de breadcrumbs automatiques
[
    {"category": "graphql", "message": "Query: products", "level": "info"},
    {"category": "graphql", "message": "Mutation: create_order", "level": "info"},
    {"category": "db", "message": "SELECT ...", "level": "debug"},
]
```

### Filtrage des Données Sensibles

```python
sentry_sdk.init(
    # ...
    before_send=lambda event, hint: filter_sensitive_data(event),
)

def filter_sensitive_data(event):
    """
    Supprime les données sensibles avant envoi à Sentry.
    """
    if "extra" in event:
        # Supprimer les tokens
        if "variables" in event["extra"]:
            vars = event["extra"]["variables"]
            for key in ["password", "token", "secret"]:
                if key in vars:
                    vars[key] = "[REDACTED]"
    return event
```

---

## OpenTelemetry

### Installation

```bash
pip install opentelemetry-api opentelemetry-sdk
pip install opentelemetry-instrumentation-django
pip install opentelemetry-instrumentation-graphene
pip install opentelemetry-exporter-otlp
```

### Configuration

```python
# root/settings/base.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.graphene import GrapheneInstrumentor

# Configuration du provider
resource = Resource(attributes={
    SERVICE_NAME: "mon-projet-api",
    "service.version": os.environ.get("APP_VERSION", "1.0.0"),
    "deployment.environment": os.environ.get("DJANGO_ENV", "development"),
})

provider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(OTLPSpanExporter(
    endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317"),
))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

# Instrumentation automatique
DjangoInstrumentor().instrument()
GrapheneInstrumentor().instrument()
```

### Configuration Rail Django

```python
RAIL_DJANGO_GRAPHQL = {
    "monitoring_settings": {
        "enable_opentelemetry": True,
        "otel_service_name": "mon-projet-api",
        "otel_exporter_endpoint": os.environ.get("OTEL_ENDPOINT"),
    },
}
```

### Traces GraphQL

Chaque opération GraphQL crée automatiquement des spans :

```
┌─────────────────────────────────────────────────────────────┐
│ graphql.operation: Query products                           │
│ ├── graphql.resolve: products                               │
│ │   ├── db.query: SELECT * FROM store_product...            │
│ │   └── graphql.resolve: category                           │
│ │       └── db.query: SELECT * FROM store_category...       │
│ └── graphql.serialize                                       │
└─────────────────────────────────────────────────────────────┘
```

### Attributs des Spans

| Attribut                 | Description                   |
| ------------------------ | ----------------------------- |
| `graphql.operation.name` | Nom de l'opération            |
| `graphql.operation.type` | query, mutation, subscription |
| `graphql.field.name`     | Nom du champ résolu           |
| `graphql.field.type`     | Type GraphQL du champ         |
| `db.statement`           | Requête SQL (tronquée)        |
| `http.status_code`       | Code HTTP de réponse          |

### Traces Personnalisées

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def resolve_complex_calculation(root, info, **kwargs):
    with tracer.start_as_current_span("complex_calculation") as span:
        span.set_attribute("input_size", len(kwargs.get("items", [])))

        result = perform_calculation(**kwargs)

        span.set_attribute("result_count", len(result))
        return result
```

---

## Métriques Prometheus

### Installation

```bash
pip install django-prometheus
```

### Configuration

```python
# root/settings/base.py
INSTALLED_APPS = [
    # ...
    "django_prometheus",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    # ... autres middlewares ...
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]
```

```python
# root/urls.py
urlpatterns = [
    # ...
    path("", include("django_prometheus.urls")),
]
```

### Métriques Rail Django

```python
RAIL_DJANGO_GRAPHQL = {
    "monitoring_settings": {
        "enable_metrics": True,
        "metrics_backend": "prometheus",
    },
}
```

### Métriques Exposées

```prometheus
# Compteur de requêtes GraphQL
rail_graphql_requests_total{operation_type="query",operation_name="products"} 1542

# Histogramme de durée
rail_graphql_request_duration_seconds_bucket{operation_type="query",le="0.1"} 1200
rail_graphql_request_duration_seconds_bucket{operation_type="query",le="0.5"} 1500

# Compteur d'erreurs
rail_graphql_errors_total{error_type="validation",operation_name="create_order"} 45

# Gauge de connexions actives
rail_graphql_active_subscriptions 12

# Compteur de rate limiting
rail_rate_limit_exceeded_total{endpoint="/graphql/"} 23
```

### Endpoint

```
GET /metrics/
```

---

## Logging Structuré

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
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if not DEBUG else "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/app.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "formatter": "json",
        },
    },
    "loggers": {
        "rail_django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "graphql": {
            "handlers": ["console"],
            "level": "INFO" if not DEBUG else "DEBUG",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",  # "DEBUG" pour voir les SQL
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
```

### Format JSON

```json
{
  "asctime": "2026-01-16T13:15:00.123456",
  "levelname": "INFO",
  "name": "rail_django.middleware",
  "message": "GraphQL operation completed",
  "operation_type": "mutation",
  "operation_name": "create_order",
  "duration_ms": 45.2,
  "user_id": 123,
  "status": "success"
}
```

### Logging des Requêtes

```python
RAIL_DJANGO_GRAPHQL = {
    "middleware_settings": {
        "enable_logging_middleware": True,
        "log_queries": True,
        "log_mutations": True,
        "log_introspection": False,
        "log_errors": True,
        "log_performance": True,
        "performance_threshold_ms": 1000,
    },
}
```

---

## Configuration Avancée

### Tableau de Bord Grafana

Importez le dashboard Rail Django pour Grafana :

1. Ouvrez Grafana
2. Import Dashboard → ID: `XXXXX`
3. Sélectionnez votre datasource Prometheus

### Alertes

Exemple de règles d'alerte Prometheus :

```yaml
# prometheus/rules/rail_django.yml
groups:
  - name: rail_django
    rules:
      - alert: HighErrorRate
        expr: rate(rail_graphql_errors_total[5m]) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High GraphQL error rate"

      - alert: SlowQueries
        expr: histogram_quantile(0.95, rate(rail_graphql_request_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "P95 query latency above 1s"
```

### Variables d'Environnement

| Variable                      | Description            | Défaut            |
| ----------------------------- | ---------------------- | ----------------- |
| `SENTRY_DSN`                  | DSN Sentry             | (désactivé)       |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Endpoint OTLP          | `localhost:4317`  |
| `OTEL_SERVICE_NAME`           | Nom du service         | `rail-django-app` |
| `PROMETHEUS_MULTIPROC_DIR`    | Dir pour multi-process | `/tmp/prometheus` |

---

## Bonnes Pratiques

### 1. Échantillonnage en Production

```python
# Ne pas tracer 100% des requêtes en prod
sentry_sdk.init(
    traces_sample_rate=0.1,  # 10%
)
```

### 2. Filtrez les Données Sensibles

```python
# Jamais de tokens/passwords dans les traces
span.set_attribute("user.id", user.id)
# span.set_attribute("user.password", ...)  # ❌ JAMAIS
```

### 3. Nommez vos Spans

```python
# ✅ Noms descriptifs
with tracer.start_span("order.calculate_total"):
    ...

# ❌ Noms génériques
with tracer.start_span("function"):
    ...
```

### 4. Centralisez les Logs

Utilisez un agrégateur (ELK, Loki, CloudWatch) pour centraliser les logs de tous les containers.

---

## Voir Aussi

- [Health Monitoring](./health.md) - Endpoints de santé
- [Audit](./audit.md) - Logging des événements métier
- [Configuration](../graphql/configuration.md) - Paramètres monitoring
