# Webhooks

## Vue d'Ensemble

Les webhooks permettent d'envoyer des événements de cycle de vie des modèles Django (create, update, delete) vers des systèmes externes. Rail Django offre une implémentation complète avec signature HMAC, authentification OAuth, filtrage de modèles et retry automatique.

---

## Table des Matières

1. [Configuration](#configuration)
2. [Structure du Payload](#structure-du-payload)
3. [Filtrage des Modèles](#filtrage-des-modèles)
4. [Filtrage et Masquage des Champs](#filtrage-et-masquage-des-champs)
5. [Signature et Sécurité](#signature-et-sécurité)
6. [Authentification des Endpoints](#authentification-des-endpoints)
7. [Delivery Asynchrone](#delivery-asynchrone)
8. [Retries et Gestion des Erreurs](#retries-et-gestion-des-erreurs)
9. [Exemples Complets](#exemples-complets)
10. [Bonnes Pratiques](#bonnes-pratiques)

---

## Configuration

### Configuration Basique

Créez ou modifiez `root/webhooks.py` :

```python
# root/webhooks.py
RAIL_DJANGO_WEBHOOKS = {
    "enabled": True,
    "endpoints": [
        {
            "name": "orders_webhook",
            "url": "https://api.example.com/webhooks/orders",
            "include_models": ["store.Order"],
        },
    ],
    "events": {
        "created": True,
        "updated": True,
        "deleted": True,
    },
}
```

### Configuration Complète

```python
# root/webhooks.py
RAIL_DJANGO_WEBHOOKS = {
    # Activation globale
    "enabled": True,

    # ─── Filtrage Global ───
    "include_models": [],  # Vide = tous les modèles
    "exclude_models": ["auth.Session", "contenttypes.ContentType"],

    # ─── Événements ───
    "events": {
        "created": True,
        "updated": True,
        "deleted": True,
    },

    # ─── Filtrage de Champs ───
    "include_fields": {},  # {"app.Model": ["field1", "field2"]}
    "exclude_fields": {},  # {"app.Model": ["internal_notes"]}
    "redact_fields": ["password", "token", "secret"],  # Masquage global
    "redaction_mask": "[REDACTED]",

    # ─── Delivery ───
    "timeout_seconds": 10,
    "async_backend": "thread",  # "thread", "sync", "custom"

    # ─── Retries ───
    "max_retries": 3,
    "retry_statuses": [408, 429, 500, 502, 503, 504],
    "retry_backoff_seconds": 1,
    "retry_backoff_factor": 2,
    "retry_jitter_seconds": 0.5,

    # ─── Endpoints ───
    "endpoints": [
        # ... voir section Endpoints
    ],
}
```

### Wiring dans Settings

```python
# root/settings/base.py
from root.webhooks import RAIL_DJANGO_WEBHOOKS

RAIL_DJANGO_GRAPHQL = {
    "webhook_settings": RAIL_DJANGO_WEBHOOKS,
    # ... autres paramètres
}
```

---

## Structure du Payload

Chaque webhook envoie un payload JSON avec cette structure :

```json
{
  "event_id": "9b1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
  "event_type": "created",
  "event_source": "model",
  "timestamp": "2026-01-16T10:30:00.123456+00:00",
  "model": "store.Order",
  "model_label": "store.order",
  "app_label": "store",
  "model_name": "order",
  "pk": 42,
  "data": {
    "id": 42,
    "reference": "ORD-2026-0042",
    "status": "pending",
    "total": "129.00",
    "customer_id": 15,
    "created_at": "2026-01-16T10:30:00Z"
  },
  "update_fields": ["status", "total"]
}
```

### Champs du Payload

| Champ           | Type       | Description                                 |
| --------------- | ---------- | ------------------------------------------- |
| `event_id`      | string     | UUID unique de l'événement                  |
| `event_type`    | string     | `created`, `updated`, ou `deleted`          |
| `event_source`  | string     | Source de l'événement (toujours `model`)    |
| `timestamp`     | string     | Horodatage ISO 8601 avec timezone           |
| `model`         | string     | Label complet du modèle (`app.Model`)       |
| `pk`            | int/string | Clé primaire de l'instance                  |
| `data`          | object     | Données sérialisées de l'instance           |
| `update_fields` | array      | Champs modifiés (uniquement pour `updated`) |

### Notes sur les Données

- Les ForeignKey utilisent l'`attname` (ex: `customer_id` au lieu de `customer`).
- Les bytes sont décodés en UTF-8 (fallback en hex).
- Les FileField retournent `url` ou `name`.
- Les relations inversées ne sont pas incluses.

---

## Filtrage des Modèles

### Niveaux de Filtrage

Le filtrage s'applique à deux niveaux :

1. **Global** : `include_models` / `exclude_models` dans la config racine
2. **Par Endpoint** : Override par endpoint

### Sélecteurs Supportés

| Sélecteur   | Description                | Exemple         |
| ----------- | -------------------------- | --------------- |
| `app.Model` | Label complet              | `"store.Order"` |
| `app`       | Tous les modèles d'une app | `"store"`       |
| `*`         | Tous les modèles           | `"*"`           |

### Logique de Résolution

```
Si include_models global ET endpoint définis :
    → Intersection des deux listes

Si exclude_models global ET endpoint définis :
    → Union des deux listes (les deux s'appliquent)
```

### Exemple

```python
RAIL_DJANGO_WEBHOOKS = {
    # Global : uniquement les apps store et crm
    "include_models": ["store", "crm"],
    "exclude_models": ["store.InternalLog"],

    "endpoints": [
        {
            "name": "orders_only",
            "url": "https://...",
            # Override : uniquement Order dans store
            "include_models": ["store.Order"],
        },
        {
            "name": "all_crm",
            "url": "https://...",
            # Hérite du global : tous les modèles crm
            "include_models": ["crm"],
        },
    ],
}
```

---

## Filtrage et Masquage des Champs

### Inclusion/Exclusion de Champs

Contrôlez quels champs sont inclus dans le payload :

```python
RAIL_DJANGO_WEBHOOKS = {
    # Inclure uniquement ces champs (allowlist)
    "include_fields": {
        "store.order": ["id", "reference", "status", "total"],
    },

    # Exclure ces champs (blocklist)
    "exclude_fields": {
        "store.order": ["internal_notes", "margin"],
        "auth.user": ["password", "last_login"],
    },
}
```

### Masquage (Redaction)

Remplacez les valeurs sensibles par un masque :

```python
RAIL_DJANGO_WEBHOOKS = {
    # Masquage global (tous les modèles)
    "redact_fields": ["password", "token", "api_key", "secret"],
    "redaction_mask": "[REDACTED]",

    # Ou par modèle
    "redact_fields": {
        "auth.user": ["password"],
        "store.payment": ["card_number", "cvv"],
    },
}
```

**Résultat :**

```json
{
  "data": {
    "username": "john.doe",
    "password": "[REDACTED]",
    "api_key": "[REDACTED]"
  }
}
```

---

## Signature et Sécurité

### Signature HMAC

Signez les payloads pour que le destinataire puisse vérifier leur authenticité :

```python
{
    "name": "secure_endpoint",
    "url": "https://api.example.com/webhooks",
    "signing_secret": "votre_secret_tres_long_et_aleatoire",
    "signing_header": "X-Rail-Signature",  # Header contenant la signature
    "signature_prefix": "sha256=",  # Préfixe de la signature
}
```

### Vérification Côté Destinataire

```python
import hmac
import hashlib

def verify_webhook_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    """
    Vérifie la signature HMAC d'un webhook Rail Django.

    Args:
        payload_body: Corps de la requête en bytes
        signature: Valeur du header X-Rail-Signature
        secret: Secret partagé

    Returns:
        True si la signature est valide
    """
    expected = "sha256=" + hmac.new(
        secret.encode(),
        payload_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


# Exemple Flask
@app.route("/webhooks/orders", methods=["POST"])
def handle_order_webhook():
    signature = request.headers.get("X-Rail-Signature")
    if not verify_webhook_signature(request.data, signature, WEBHOOK_SECRET):
        return "Invalid signature", 401

    event = request.get_json()
    # Traiter l'événement...
    return "OK", 200
```

---

## Authentification des Endpoints

### Token Statique

```python
{
    "name": "api_with_token",
    "url": "https://api.example.com/webhooks",
    "headers": {
        "Authorization": "Bearer mon_token_statique",
        "X-Api-Key": "ma_cle_api",
    },
}
```

### OAuth2 / Token Dynamique

Utilisez un provider de token pour obtenir des tokens frais :

```python
{
    "name": "oauth_endpoint",
    "url": "https://api.example.com/webhooks",

    # Provider de token
    "auth_token_path": "rail_django.webhooks.auth.fetch_auth_token",

    # Configuration OAuth
    "auth_url": "https://auth.example.com/oauth/token",
    "auth_payload": {
        "client_id": "votre_client_id",
        "client_secret": "votre_client_secret",
        "grant_type": "client_credentials",
    },
    "auth_token_field": "access_token",  # Champ dans la réponse

    # Header et schéma
    "auth_header": "Authorization",
    "auth_scheme": "Bearer",
}
```

### Provider Personnalisé

```python
# myapp/webhooks.py
def my_token_provider(endpoint, payload, payload_json):
    """
    Provider de token personnalisé.

    Args:
        endpoint: Configuration de l'endpoint
        payload: Dictionnaire du payload
        payload_json: JSON sérialisé du payload

    Returns:
        Token d'authentification
    """
    # Logique personnalisée (vault, cache, etc.)
    return get_token_from_vault(endpoint.name)
```

```python
{
    "auth_token_path": "myapp.webhooks.my_token_provider",
}
```

---

## Delivery Asynchrone

### Backend Thread (Défaut)

Utilise un pool de threads in-process :

```python
"async_backend": "thread",
```

### Backend Synchrone

Pour tests ou environnements simples :

```python
"async_backend": "sync",
```

### Backend Personnalisé (Celery, etc.)

Déléguez à une file de tâches :

```python
"async_backend": "custom",
"async_task_path": "myapp.tasks.enqueue_webhook",
```

```python
# myapp/tasks.py
from celery import shared_task

@shared_task
def deliver_webhook(endpoint_config, payload):
    """Tâche Celery pour la livraison."""
    from rail_django.webhooks import WebhookDispatcher
    dispatcher = WebhookDispatcher(endpoint_config)
    dispatcher.send(payload)

def enqueue_webhook(endpoint, payload, settings):
    """
    Point d'entrée appelé par Rail Django.
    """
    deliver_webhook.delay(endpoint, payload)
```

---

## Retries et Gestion des Erreurs

### Configuration des Retries

```python
RAIL_DJANGO_WEBHOOKS = {
    # Nombre maximum de tentatives
    "max_retries": 3,

    # Codes HTTP déclenchant un retry
    "retry_statuses": [408, 429, 500, 502, 503, 504],

    # Délai initial entre retries
    "retry_backoff_seconds": 1,

    # Facteur exponentiel (1, 2, 4, 8...)
    "retry_backoff_factor": 2,

    # Jitter aléatoire (évite les thundering herds)
    "retry_jitter_seconds": 0.5,
}
```

### Calcul du Délai

```
Délai(n) = retry_backoff_seconds * (retry_backoff_factor ^ n) + random(0, retry_jitter_seconds)

Exemple avec les valeurs par défaut :
  Retry 1: 1 * 2^0 + jitter = ~1.3s
  Retry 2: 1 * 2^1 + jitter = ~2.4s
  Retry 3: 1 * 2^2 + jitter = ~4.5s
```

### Comportement en Échec

Après épuisement des retries :

1. L'événement est loggé avec le code d'erreur.
2. L'événement est abandonné (pas de persistance par défaut).

Pour la persistance, utilisez un backend custom avec une dead letter queue.

---

## Exemples Complets

### Configuration Multi-Endpoints

```python
# root/webhooks.py
RAIL_DJANGO_WEBHOOKS = {
    "enabled": True,

    # Exclusions globales
    "exclude_models": [
        "auth.Session",
        "django.ContentType",
        "audit.AuditEvent",
    ],

    # Masquage global
    "redact_fields": ["password", "token", "secret_key"],

    "endpoints": [
        # Endpoint Orders - système de facturation
        {
            "name": "billing_orders",
            "url": "https://billing.internal.corp/webhooks/orders",
            "include_models": ["store.Order"],
            "events": {"created": True, "updated": True},
            "signing_secret": os.environ.get("BILLING_WEBHOOK_SECRET"),
            "timeout_seconds": 5,
        },

        # Endpoint CRM - toutes les entités clients
        {
            "name": "crm_sync",
            "url": "https://crm.example.com/api/webhooks",
            "include_models": ["crm.Customer", "crm.Contact", "crm.Lead"],
            "auth_token_path": "rail_django.webhooks.auth.fetch_auth_token",
            "auth_url": "https://crm.example.com/oauth/token",
            "auth_payload": {
                "client_id": os.environ.get("CRM_CLIENT_ID"),
                "client_secret": os.environ.get("CRM_CLIENT_SECRET"),
            },
            "include_fields": {
                "crm.customer": ["id", "name", "email", "phone"],
            },
        },

        # Endpoint Analytics - tous les événements
        {
            "name": "analytics",
            "url": "https://analytics.internal/events",
            "include_models": ["*"],
            "exclude_models": ["auth", "sessions"],
            "headers": {
                "X-Source": "rail-django",
                "X-Api-Key": os.environ.get("ANALYTICS_API_KEY"),
            },
        },
    ],
}
```

### Réception et Traitement (FastAPI)

```python
from fastapi import FastAPI, Request, HTTPException, Header
import hmac
import hashlib

app = FastAPI()

WEBHOOK_SECRET = "votre_secret"

@app.post("/webhooks/orders")
async def handle_order_webhook(
    request: Request,
    x_rail_signature: str = Header(None),
    x_rail_event_id: str = Header(None),
):
    """
    Récepteur de webhooks pour les commandes.
    """
    body = await request.body()

    # Vérifier la signature
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(x_rail_signature or "", expected):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parser le payload
    event = await request.json()

    # Traiter selon le type d'événement
    event_type = event["event_type"]
    order_data = event["data"]

    if event_type == "created":
        await create_invoice(order_data)
    elif event_type == "updated":
        await update_invoice(order_data)

    return {"status": "processed", "event_id": x_rail_event_id}
```

---

## Bonnes Pratiques

### 1. Sécurité

```python
# ✅ Utilisez HTTPS
"url": "https://api.example.com/webhooks",

# ✅ Signez les payloads
"signing_secret": os.environ.get("WEBHOOK_SECRET"),

# ✅ Masquez les données sensibles
"redact_fields": ["password", "ssn", "credit_card"],

# ❌ N'incluez jamais de secrets dans le payload
```

### 2. Résilience

```python
# ✅ Configurez les retries
"max_retries": 3,
"retry_backoff_factor": 2,

# ✅ Utilisez des timeouts raisonnables
"timeout_seconds": 10,

# ✅ Implémentez l'idempotence côté récepteur
# (utilisez event_id pour dédupliquer)
```

### 3. Performance

```python
# ✅ Utilisez le backend async
"async_backend": "thread",

# ✅ Limitez les champs envoyés
"include_fields": {"model": ["id", "status"]},

# ✅ Excluez les modèles non pertinents
"exclude_models": ["django_session", "admin.LogEntry"],
```

### 4. Debugging

```python
# Testez avec un endpoint local
{
    "name": "dev_debug",
    "url": "http://localhost:8001/webhooks/debug",
    "enabled": os.environ.get("DEBUG") == "True",
}
```

---

## Voir Aussi

- [Subscriptions](./subscriptions.md) - Alternative temps réel via WebSocket
- [Audit & Logging](./audit.md) - Traçabilité des événements système
- [Configuration](../graphql/configuration.md) - Référence complète des paramètres
