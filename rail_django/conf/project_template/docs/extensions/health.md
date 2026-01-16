# Monitoring Santé (Health Checks)

## Vue d'Ensemble

Rail Django expose des endpoints de santé pour les orchestrateurs (Kubernetes, load balancers) et le monitoring. Ces endpoints vérifient l'état des composants critiques : base de données, cache, services externes.

---

## Table des Matières

1. [Endpoints Disponibles](#endpoints-disponibles)
2. [Configuration](#configuration)
3. [Query GraphQL](#query-graphql)
4. [Composants Vérifiés](#composants-vérifiés)
5. [Dashboard](#dashboard)
6. [Intégration Kubernetes](#intégration-kubernetes)
7. [Bonnes Pratiques](#bonnes-pratiques)

---

## Endpoints Disponibles

### URLs Simples

Ajoutez dans `urls.py` :

```python
from rail_django.health_urls import health_urlpatterns

urlpatterns = [
    # ... vos URLs
] + health_urlpatterns
```

| Endpoint          | Description                      |
| ----------------- | -------------------------------- |
| `/health/`        | Dashboard HTML                   |
| `/health/api/`    | Status JSON complet              |
| `/health/check/`  | Vérification rapide (200 ou 503) |
| `/health/ping/`   | Ping simple (toujours 200)       |
| `/health/status/` | Alias de `/health/check/`        |

### URLs Complètes

Pour plus de fonctionnalités :

```python
from rail_django.views.health_views import get_health_urls

urlpatterns = [
    # ... vos URLs
] + get_health_urls()
```

| Endpoint              | Description                |
| --------------------- | -------------------------- |
| `/health/`            | Dashboard HTML interactif  |
| `/health/api/`        | Status JSON détaillé       |
| `/health/metrics/`    | Métriques Prometheus-style |
| `/health/components/` | État par composant         |
| `/health/history/`    | Historique des checks      |

---

## Configuration

### Paramètres de Health

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "health_settings": {
        # Active le health check
        "enabled": True,

        # Composants à vérifier
        "check_database": True,
        "check_cache": True,
        "check_disk": True,
        "check_memory": True,
        "check_external_services": True,

        # Seuils d'alerte
        "disk_usage_warning_percent": 80,
        "disk_usage_critical_percent": 95,
        "memory_usage_warning_percent": 80,
        "memory_usage_critical_percent": 95,

        # Services externes à vérifier
        "external_services": [
            {
                "name": "payment_gateway",
                "url": "https://api.stripe.com/v1/health",
                "timeout_seconds": 5,
            },
            {
                "name": "email_service",
                "url": "https://api.sendgrid.com/v3/health",
                "timeout_seconds": 5,
            },
        ],

        # Historique
        "history_retention_hours": 24,
        "history_max_entries": 1000,
    },
}
```

---

## Query GraphQL

### Health Query

```graphql
query HealthStatus {
  health {
    health_status {
      overall_status # "healthy", "degraded", "unhealthy"
      components {
        databases {
          status # "healthy", "unhealthy"
          message
          latency_ms
        }
        cache {
          status
          message
          latency_ms
        }
        disk {
          status
          usage_percent
          free_bytes
        }
        memory {
          status
          usage_percent
          available_bytes
        }
        external_services {
          name
          status
          latency_ms
          message
        }
      }

      system_metrics {
        cpu_usage_percent
        memory_usage_percent
        disk_usage_percent
        open_connections
        uptime_seconds
      }

      last_check
      version
    }
  }
}
```

### Réponse Exemple

```json
{
  "data": {
    "health": {
      "health_status": {
        "overall_status": "healthy",
        "components": {
          "databases": {
            "status": "healthy",
            "message": "PostgreSQL connected",
            "latency_ms": 2.5
          },
          "cache": {
            "status": "healthy",
            "message": "Redis connected",
            "latency_ms": 0.8
          },
          "disk": {
            "status": "healthy",
            "usage_percent": 45.2,
            "free_bytes": 52428800000
          },
          "memory": {
            "status": "healthy",
            "usage_percent": 62.1,
            "available_bytes": 4294967296
          },
          "external_services": [
            {
              "name": "payment_gateway",
              "status": "healthy",
              "latency_ms": 150,
              "message": "OK"
            }
          ]
        },
        "system_metrics": {
          "cpu_usage_percent": 25.5,
          "memory_usage_percent": 62.1,
          "disk_usage_percent": 45.2,
          "open_connections": 42,
          "uptime_seconds": 864000
        },
        "last_check": "2026-01-16T10:30:00Z",
        "version": "1.0.0"
      }
    }
  }
}
```

---

## Composants Vérifiés

### Base de Données

Effectue une requête simple pour vérifier la connectivité :

```python
# Vérification effectuée
connection.ensure_connection()
cursor.execute("SELECT 1")
```

**Status possibles :**

- `healthy` : Connexion réussie
- `unhealthy` : Connexion échouée, timeout

### Cache

Vérifie la connectivité au cache (Redis, Memcached) :

```python
# Vérification effectuée
cache.set("health_check", "1", timeout=10)
value = cache.get("health_check")
```

### Disque

Vérifie l'espace disponible :

```python
# Seuils par défaut
"disk_usage_warning_percent": 80,   # → status: "degraded"
"disk_usage_critical_percent": 95,  # → status: "unhealthy"
```

### Mémoire

Vérifie l'utilisation mémoire :

```python
# Seuils par défaut
"memory_usage_warning_percent": 80,
"memory_usage_critical_percent": 95,
```

### Services Externes

Vérifie les APIs externes configurées :

```python
"external_services": [
    {
        "name": "payment_gateway",
        "url": "https://api.stripe.com/v1/health",
        "timeout_seconds": 5,
        "method": "GET",  # GET ou HEAD
        "expected_status": 200,
        "headers": {"Authorization": "Bearer xxx"},
    },
]
```

---

## Dashboard

### Interface HTML

Accédez à `/health/` pour un dashboard interactif :

- Vue d'ensemble avec indicateurs colorés
- Détails par composant
- Historique des derniers checks
- Graphiques d'utilisation (si activés)

### Personnalisation

```python
RAIL_DJANGO_GRAPHQL = {
    "health_settings": {
        "dashboard_theme": "dark",  # "light" ou "dark"
        "dashboard_refresh_seconds": 30,
        "dashboard_show_history": True,
    },
}
```

---

## Intégration Kubernetes

### Liveness Probe

Vérifie que l'application répond :

```yaml
# kubernetes/deployment.yaml
livenessProbe:
  httpGet:
    path: /health/ping/
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30
  failureThreshold: 3
```

### Readiness Probe

Vérifie que l'application est prête à recevoir du trafic :

```yaml
readinessProbe:
  httpGet:
    path: /health/check/
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3
```

### Startup Probe

Pour les démarrages lents :

```yaml
startupProbe:
  httpGet:
    path: /health/ping/
    port: 8000
  initialDelaySeconds: 0
  periodSeconds: 5
  failureThreshold: 30 # 30 × 5s = 2.5 min max startup
```

### Codes de Réponse

| Endpoint         | Success | Failure                        |
| ---------------- | ------- | ------------------------------ |
| `/health/ping/`  | 200     | (toujours 200)                 |
| `/health/check/` | 200     | 503                            |
| `/health/api/`   | 200     | 200 (avec status dans le body) |

---

## Alerting

### Webhooks de Santé

Configurez des notifications sur changement d'état :

```python
RAIL_DJANGO_GRAPHQL = {
    "health_settings": {
        "alert_on_status_change": True,
        "alert_webhook_url": "https://hooks.slack.com/services/xxx",
        "alert_min_severity": "degraded",  # "degraded" ou "unhealthy"
    },
}
```

### Custom Health Check

Ajoutez vos propres vérifications :

```python
from rail_django.extensions.health import register_health_check

@register_health_check("custom_service")
def check_custom_service():
    """
    Vérifie un service personnalisé.

    Returns:
        dict: {"status": "healthy"|"degraded"|"unhealthy", "message": "..."}
    """
    try:
        response = custom_client.ping()
        return {
            "status": "healthy",
            "message": "Custom service OK",
            "latency_ms": response.latency,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "message": str(e),
        }
```

---

## Bonnes Pratiques

### 1. Endpoints Séparés

```yaml
# ✅ Utilisez ping/ pour liveness (pas de vérification DB)
livenessProbe:
  httpGet:
    path: /health/ping/

# ✅ Utilisez check/ pour readiness (vérifie les dépendances)
readinessProbe:
  httpGet:
    path: /health/check/
```

### 2. Timeouts Appropriés

```python
# ✅ Timeouts courts pour les health checks
"external_services": [
    {
        "name": "api",
        "url": "https://...",
        "timeout_seconds": 3,  # Court pour ne pas bloquer
    },
]
```

### 3. N'Exposez pas Trop d'Infos

```python
# ✅ En production, limitez les détails
if not settings.DEBUG:
    "hide_detailed_errors": True,
    "hide_version": True,
```

### 4. Monitoring Continu

Intégrez avec votre stack de monitoring :

```python
# Prometheus metrics endpoint
# GET /health/metrics/

# Exemple de métriques exposées
rail_health_status{component="database"} 1
rail_health_latency_seconds{component="database"} 0.002
rail_health_check_total 15234
```

---

## Voir Aussi

- [Configuration](../graphql/configuration.md) - Paramètres health_settings
- [Déploiement Production](../deployment/production.md) - Checklist de déploiement
- [Observabilité](./observability.md) - Sentry et OpenTelemetry
