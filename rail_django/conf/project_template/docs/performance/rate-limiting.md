# Rate Limiting

## Vue d'Ensemble

Rail Django intègre un système de rate limiting pour protéger votre API contre les abus. Le rate limiting s'applique aux requêtes GraphQL, aux endpoints REST et peut être configuré par utilisateur, IP ou endpoint.

---

## Table des Matières

1. [Configuration Globale](#configuration-globale)
2. [Stratégies de Limiting](#stratégies-de-limiting)
3. [Contextes de Rate Limiting](#contextes-de-rate-limiting)
4. [Headers de Réponse](#headers-de-réponse)
5. [Personnalisation](#personnalisation)
6. [Bonnes Pratiques](#bonnes-pratiques)

---

## Configuration Globale

### Paramètres de Base

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_rate_limiting": True,
        "rate_limit_requests_per_minute": 60,
        "rate_limit_requests_per_hour": 1000,
    },
    "middleware_settings": {
        "enable_rate_limiting_middleware": True,
    },
}
```

### Configuration Avancée

```python
RAIL_DJANGO_RATE_LIMITING = {
    # ─── Activation ───
    "enabled": True,

    # ─── Backend de Stockage ───
    "backend": "redis",  # "redis", "memory", ou "django_cache"
    "redis_url": os.environ.get("REDIS_URL", "redis://localhost:6379/1"),

    # ─── Limites par Défaut ───
    "default_limits": {
        "per_second": None,      # Pas de limite par seconde
        "per_minute": 60,
        "per_hour": 1000,
        "per_day": 10000,
    },

    # ─── Identification ───
    "key_function": "rail_django.rate_limiting.get_rate_limit_key",
    "key_prefix": "rl:",

    # ─── Comportement ───
    "include_headers": True,     # Ajoute les headers X-RateLimit-*
    "on_reject": "error",        # "error" ou "delay"
    "error_message": "Rate limit exceeded. Please slow down.",

    # ─── Contextes Spécifiques ───
    "contexts": {
        # ... voir section Contextes
    },
}
```

---

## Stratégies de Limiting

### Par Utilisateur Authentifié

```python
RAIL_DJANGO_RATE_LIMITING = {
    "default_limits": {
        "per_minute": 60,
    },
    "key_function": "rail_django.rate_limiting.user_key",
}
```

Le rate limit est appliqué par `user.id` pour les utilisateurs authentifiés.

### Par Adresse IP

```python
RAIL_DJANGO_RATE_LIMITING = {
    "key_function": "rail_django.rate_limiting.ip_key",
}
```

Utilise l'IP du client (détectée via X-Forwarded-For si configuré).

### Combiné (Utilisateur ou IP)

```python
RAIL_DJANGO_RATE_LIMITING = {
    "key_function": "rail_django.rate_limiting.user_or_ip_key",
}
```

Utilise l'ID utilisateur si authentifié, sinon l'IP.

### Par Token API

```python
def api_token_key(request):
    """
    Rate limit par token API.
    """
    token = request.headers.get("X-API-Token")
    if token:
        return f"token:{token}"
    return f"ip:{get_client_ip(request)}"

RAIL_DJANGO_RATE_LIMITING = {
    "key_function": "myapp.rate_limiting.api_token_key",
}
```

---

## Contextes de Rate Limiting

Appliquez des limites différentes selon le contexte.

### Configuration des Contextes

```python
RAIL_DJANGO_RATE_LIMITING = {
    "contexts": {
        # API GraphQL principale
        "graphql": {
            "per_minute": 100,
            "per_hour": 2000,
        },

        # Authentification (plus restrictif)
        "auth": {
            "per_minute": 10,
            "per_hour": 50,
            "error_message": "Too many login attempts. Please wait.",
        },

        # API Schema Management (admin)
        "schema_api": {
            "per_minute": 30,
            "per_hour": 200,
        },

        # Exports (très limité)
        "export": {
            "per_minute": 5,
            "per_hour": 50,
        },

        # Utilisateurs premium (plus généreux)
        "premium": {
            "per_minute": 500,
            "per_hour": 10000,
        },
    },
}
```

### Sélection du Contexte

```python
def get_rate_limit_context(request):
    """
    Détermine le contexte de rate limiting.
    """
    # Premium users
    if hasattr(request, "user") and request.user.is_premium:
        return "premium"

    # Auth endpoints
    if "/auth/" in request.path:
        return "auth"

    # Export endpoints
    if "/export/" in request.path:
        return "export"

    return "graphql"

RAIL_DJANGO_RATE_LIMITING = {
    "context_function": "myapp.rate_limiting.get_rate_limit_context",
}
```

### Limites par Rôle

```python
RAIL_DJANGO_RATE_LIMITING = {
    "role_limits": {
        "admin": {
            "per_minute": 500,
            "per_hour": 10000,
        },
        "api_client": {
            "per_minute": 1000,
            "per_hour": 50000,
        },
        "default": {
            "per_minute": 60,
            "per_hour": 1000,
        },
    },
}
```

---

## Headers de Réponse

Quand `include_headers: True`, les réponses incluent :

| Header                  | Description                               |
| ----------------------- | ----------------------------------------- |
| `X-RateLimit-Limit`     | Limite maximale pour la fenêtre           |
| `X-RateLimit-Remaining` | Requêtes restantes                        |
| `X-RateLimit-Reset`     | Timestamp Unix de réinitialisation        |
| `X-RateLimit-Window`    | Type de fenêtre (minute, hour, day)       |
| `Retry-After`           | Secondes avant prochain essai (si limité) |

### Exemple de Réponse

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1705405200
X-RateLimit-Window: minute
```

### Réponse Quand Limité

```http
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1705405200
Retry-After: 35
Content-Type: application/json

{
  "errors": [{
    "message": "Rate limit exceeded. Please slow down.",
    "extensions": {
      "code": "RATE_LIMITED",
      "retryAfter": 35
    }
  }]
}
```

---

## Personnalisation

### Fonction de Clé Personnalisée

```python
# myapp/rate_limiting.py
def custom_rate_limit_key(request):
    """
    Génère une clé de rate limit personnalisée.

    La clé détermine le "bucket" de comptage.
    """
    # Par organisation
    if hasattr(request, "user") and request.user.organization_id:
        return f"org:{request.user.organization_id}"

    # Par IP pour les anonymes
    return f"ip:{get_client_ip(request)}"
```

### Limites Dynamiques

```python
def get_dynamic_limits(request):
    """
    Retourne les limites basées sur l'utilisateur.
    """
    if hasattr(request, "user"):
        tier = getattr(request.user, "subscription_tier", "free")

        if tier == "enterprise":
            return {"per_minute": 1000, "per_hour": 50000}
        elif tier == "pro":
            return {"per_minute": 200, "per_hour": 5000}

    return {"per_minute": 30, "per_hour": 500}

RAIL_DJANGO_RATE_LIMITING = {
    "limits_function": "myapp.rate_limiting.get_dynamic_limits",
}
```

### Exemptions

```python
RAIL_DJANGO_RATE_LIMITING = {
    "exempt_paths": [
        "/health/",
        "/health/ping/",
        "/static/",
    ],
    "exempt_ips": [
        "127.0.0.1",
        "10.0.0.0/8",  # Réseau interne
    ],
    "exempt_users": [
        "service_account",
    ],
}
```

### Handler Personnalisé

```python
def on_rate_limit_exceeded(request, limit_info):
    """
    Appelé quand la limite est dépassée.
    """
    # Log l'événement
    logger.warning(
        "Rate limit exceeded",
        extra={
            "user_id": getattr(request.user, "id", None),
            "ip": get_client_ip(request),
            "limit": limit_info["limit"],
            "window": limit_info["window"],
        }
    )

    # Optionnel : alerter si abuse sévère
    if limit_info["consecutive_hits"] > 10:
        send_abuse_alert(request)

RAIL_DJANGO_RATE_LIMITING = {
    "on_exceed_callback": "myapp.rate_limiting.on_rate_limit_exceeded",
}
```

---

## Bonnes Pratiques

### 1. Utilisez Redis en Production

```python
# ✅ Redis pour le rate limiting distribué
RAIL_DJANGO_RATE_LIMITING = {
    "backend": "redis",
    "redis_url": os.environ.get("REDIS_URL"),
}

# ❌ Memory backend ne fonctionne pas avec plusieurs workers
# "backend": "memory",  # Seulement pour dev/tests
```

### 2. Différenciez par Contexte

```python
# ✅ Limites adaptées au contexte
"contexts": {
    "auth": {"per_minute": 5},      # Très restrictif
    "graphql": {"per_minute": 100}, # Normal
    "export": {"per_minute": 2},    # Très limité
}
```

### 3. Communiquez les Limites

```python
# ✅ Incluez les headers
"include_headers": True,

# ✅ Messages clairs
"error_message": "Vous avez dépassé la limite de requêtes. Réessayez dans {retry_after} secondes.",
```

### 4. Exemptez les Health Checks

```python
"exempt_paths": [
    "/health/",
    "/health/ping/",
    "/health/check/",
],
```

### 5. Monitorez les Dépassements

```python
# Log les rate limits pour analyse
"on_exceed_callback": "myapp.monitoring.log_rate_limit",

# Métriques Prometheus
"metrics_enabled": True,
```

### 6. Testez les Limites

```python
from django.test import TestCase

class RateLimitTests(TestCase):
    def test_rate_limit_exceeded(self):
        for i in range(65):  # Limite = 60/min
            response = self.client.post("/graphql/gql/", ...)

        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)
```

---

## Voir Aussi

- [Optimisation](./optimization.md) - Performance des requêtes
- [Sécurité](../security/authentication.md) - Authentification
- [Configuration](../graphql/configuration.md) - Tous les paramètres
