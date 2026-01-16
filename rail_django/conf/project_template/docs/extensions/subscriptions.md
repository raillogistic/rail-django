# Subscriptions GraphQL

## Vue d'Ensemble

Rail Django génère automatiquement des subscriptions GraphQL pour les événements create/update/delete de vos modèles Django. Cette fonctionnalité utilise Django Channels et WebSocket pour le temps réel.

---

## Table des Matières

1. [Prérequis](#prérequis)
2. [Configuration](#configuration)
3. [Configuration ASGI](#configuration-asgi)
4. [Subscriptions Générées](#subscriptions-générées)
5. [Filtrage des Événements](#filtrage-des-événements)
6. [Permissions et Sécurité](#permissions-et-sécurité)
7. [Configuration par Modèle](#configuration-par-modèle)
8. [Client Apollo (React)](#client-apollo-react)
9. [Production](#production)
10. [Dépannage](#dépannage)

---

## Prérequis

### Dépendances

Les dépendances sont incluses dans `requirements/base.txt` :

```txt
channels>=4.0.0
daphne>=4.0.0
channels-graphql-ws>=1.0.0
```

### Installation

```bash
pip install -r requirements/base.txt
```

---

## Configuration

### Activation des Subscriptions

```python
# root/settings/base.py
INSTALLED_APPS = [
    "daphne",        # Serveur ASGI
    "channels",      # Django Channels
    # ... autres apps
]

ASGI_APPLICATION = "root.asgi.application"

# Channel Layer (développement)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

RAIL_DJANGO_GRAPHQL = {
    "subscription_settings": {
        # Active la génération des subscriptions
        "enable_subscriptions": True,
        # Types d'événements
        "enable_create": True,
        "enable_update": True,
        "enable_delete": True,
        # Active les filtres sur les subscriptions
        "enable_filters": True,
        # Allowlist de modèles (vide = tous)
        "include_models": [],
        # Blocklist de modèles
        "exclude_models": ["audit.AuditEvent", "django.Session"],
    },
}
```

### Allowlist des Subscriptions (Optionnel)

Limitez les subscriptions exposées dans le schéma :

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "subscription_field_allowlist": [
            "order_created",
            "order_updated",
            "product_updated",
        ],
    },
}
```

---

## Configuration ASGI

### Fichier asgi.py

```python
# root/asgi.py
"""
Configuration ASGI pour les subscriptions GraphQL.
"""
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import path
from rail_django.extensions.subscriptions import get_subscription_consumer

# Initialisation Django (IMPORTANT: avant les imports de modèles)
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    # HTTP standard
    "http": django_asgi_app,

    # WebSocket pour subscriptions GraphQL
    "websocket": AuthMiddlewareStack(
        URLRouter([
            path("graphql/", get_subscription_consumer("gql")),
            path("graphql/graphiql/", get_subscription_consumer("gql")),
        ])
    ),
})
```

### Paramètre du Consumer

`get_subscription_consumer(schema_name)` accepte le nom du schéma :

- `"gql"` : Schéma par défaut
- `"admin"` : Schéma admin (si configuré)
- Autre nom défini dans `RAIL_DJANGO_GRAPHQL_SCHEMAS`

---

## Subscriptions Générées

### Convention de Nommage

Pour chaque modèle, trois subscriptions sont générées :

```
<model>_created
<model>_updated
<model>_deleted
```

Les noms sont en `snake_case` (ex: `order_item_created` pour `OrderItem`).

### Structure du Payload

```graphql
subscription {
  order_created {
    event # "created", "updated", ou "deleted"
    id # Clé primaire de l'instance
    node {
      # Instance complète du modèle
      id
      reference
      status
      total
      customer {
        id
        name
      }
    }
  }
}
```

### Champs de Réponse

| Champ   | Type       | Description                                        |
| ------- | ---------- | -------------------------------------------------- |
| `event` | String     | Type d'événement (`created`, `updated`, `deleted`) |
| `id`    | ID         | Clé primaire de l'objet                            |
| `node`  | ObjectType | Instance complète avec relations                   |

---

## Filtrage des Événements

Si `enable_filters: True`, les subscriptions acceptent un argument `filters` :

### Syntaxe des Filtres

```graphql
subscription FilteredOrders {
  order_created(
    filters: {
      status: { exact: "pending" }
      total: { gte: 100 }
      customer__country: { in: ["FR", "BE", "CH"] }
    }
  ) {
    event
    node {
      id
      reference
      status
      total
    }
  }
}
```

### Opérateurs Supportés

Les mêmes opérateurs que les queries list sont disponibles :

- `exact`, `iexact`
- `contains`, `icontains`
- `startswith`, `istartswith`
- `endswith`, `iendswith`
- `gt`, `gte`, `lt`, `lte`
- `in`, `isnull`
- `range`

### Comportement du Filtrage

- Pour `created` et `updated` : Le filtre est appliqué en base de données.
- Pour `deleted` : Le filtre est évalué en mémoire (l'objet n'existe plus en DB).
- Filtres invalides : L'événement est ignoré (log warning).

---

## Permissions et Sécurité

### Authentification

Les subscriptions respectent `authentication_required` :

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "authentication_required": True,
    },
}
```

Si activé, les connexions WebSocket sans token JWT valide sont refusées.

### Permissions Modèle

Les vérifications `GraphQLMeta` s'appliquent :

```python
class Order(models.Model):
    class GraphQLMeta:
        access = {
            "operations": {
                "list": {"roles": ["sales", "admin"]},
                "subscribe": {"roles": ["sales", "admin"]},  # Optionnel
            },
        }
```

Si `subscribe` n'est pas défini, la permission `list` est utilisée.

### Masquage des Champs

Le masquage par rôle s'applique au payload de subscription :

```python
class Order(models.Model):
    class GraphQLMeta:
        field_permissions = {
            "margin": {
                "roles": ["finance"],
                "visibility": "hidden",
            },
        }
```

Un utilisateur `sales` ne verra pas le champ `margin` même dans les subscriptions.

---

## Configuration par Modèle

### Via GraphQLMeta

```python
class Project(models.Model):
    """
    Projet avec configuration de subscription personnalisée.
    """
    name = models.CharField("Nom", max_length=100)
    status = models.CharField("Statut", max_length=20)

    class GraphQLMeta:
        # Activer toutes les subscriptions
        subscriptions = True

        # Ou spécifier les événements
        # subscriptions = ["create", "update"]

        # Ou configuration détaillée
        # subscriptions = {
        #     "create": True,
        #     "update": True,
        #     "delete": False,
        # }
```

### Désactiver pour un Modèle

```python
class AuditLog(models.Model):
    """
    Logs d'audit - pas de subscription.
    """
    class GraphQLMeta:
        subscriptions = False
```

---

## Client Apollo (React)

### Configuration du Client

```typescript
// src/apollo.ts
import { ApolloClient, InMemoryCache, HttpLink, split } from "@apollo/client";
import { WebSocketLink } from "@apollo/client/link/ws";
import { getMainDefinition } from "@apollo/client/utilities";

// Lien HTTP pour queries et mutations
const httpLink = new HttpLink({
  uri: "/graphql/gql/",
  headers: {
    Authorization: `Bearer ${getAccessToken()}`,
  },
});

// Lien WebSocket pour subscriptions
const wsLink = new WebSocketLink({
  uri: `ws://${window.location.host}/graphql/`,
  options: {
    reconnect: true,
    connectionParams: () => ({
      authorization: `Bearer ${getAccessToken()}`,
    }),
  },
});

// Split : WebSocket pour subscriptions, HTTP pour le reste
const link = split(
  ({ query }) => {
    const definition = getMainDefinition(query);
    return (
      definition.kind === "OperationDefinition" &&
      definition.operation === "subscription"
    );
  },
  wsLink,
  httpLink
);

export const client = new ApolloClient({
  link,
  cache: new InMemoryCache(),
});
```

### Hook useSubscription

```tsx
import { gql, useSubscription } from "@apollo/client";

const ORDER_SUBSCRIPTION = gql`
  subscription OnOrderCreated($filters: OrderComplexFilter) {
    order_created(filters: $filters) {
      event
      node {
        id
        reference
        status
        total
      }
    }
  }
`;

function OrderNotifications() {
  const { data, loading, error } = useSubscription(ORDER_SUBSCRIPTION, {
    variables: {
      filters: {
        status: { exact: "pending" },
      },
    },
    onSubscriptionData: ({ subscriptionData }) => {
      const order = subscriptionData.data?.order_created?.node;
      if (order) {
        showNotification(`Nouvelle commande: ${order.reference}`);
      }
    },
  });

  if (loading) return <p>En attente d'événements...</p>;
  if (error) return <p>Erreur: {error.message}</p>;

  return <div>Dernière commande: {data?.order_created?.node?.reference}</div>;
}
```

### Composant de Liste Temps Réel

```tsx
import { gql, useQuery, useSubscription } from "@apollo/client";
import { useCallback } from "react";

const ORDERS_QUERY = gql`
  query Orders {
    orders(order_by: ["-created_at"], limit: 100) {
      id
      reference
      status
    }
  }
`;

const ORDER_CREATED = gql`
  subscription {
    order_created {
      node {
        id
        reference
        status
      }
    }
  }
`;

const ORDER_UPDATED = gql`
  subscription {
    order_updated {
      node {
        id
        reference
        status
      }
    }
  }
`;

function OrderList() {
  const { data, refetch } = useQuery(ORDERS_QUERY);

  // Ajouter les nouvelles commandes
  useSubscription(ORDER_CREATED, {
    onSubscriptionData: () => refetch(),
  });

  // Mettre à jour les commandes existantes (Apollo Cache)
  useSubscription(ORDER_UPDATED);

  return (
    <ul>
      {data?.orders.map((order) => (
        <li key={order.id}>
          {order.reference} - {order.status}
        </li>
      ))}
    </ul>
  );
}
```

---

## Production

### Channel Layer Redis

En production, utilisez Redis pour le support multi-workers :

```bash
pip install channels-redis
```

```python
# root/settings/production.py
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(os.environ.get("REDIS_HOST", "localhost"), 6379)],
            "capacity": 1500,
            "expiry": 10,
        },
    },
}
```

### Déploiement avec Daphne

```dockerfile
# Dockerfile
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "root.asgi:application"]
```

Ou avec Uvicorn :

```dockerfile
CMD ["uvicorn", "root.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
```

### Nginx Configuration

```nginx
# /etc/nginx/conf.d/app.conf
upstream django_ws {
    server app:8000;
}

server {
    listen 443 ssl;

    location /graphql/ {
        proxy_pass http://django_ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

---

## Dépannage

### Erreur : ImportError channels-graphql-ws

**Cause :** Package non installé.

**Solution :**

```bash
pip install channels-graphql-ws
```

### Erreur : WebSocket connection failed

**Causes possibles :**

1. ASGI_APPLICATION mal configuré
2. Nginx ne forward pas les en-têtes WebSocket
3. Token JWT invalide ou expiré

**Vérifications :**

```bash
# Test direct sans Nginx
daphne -b 0.0.0.0 -p 8000 root.asgi:application
```

### Les événements ne sont pas reçus

**Causes possibles :**

1. Channel Layer InMemory avec plusieurs workers
2. Le modèle est dans `exclude_models`
3. Permissions insuffisantes

**Solution :**

```python
# Utilisez Redis en production
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        ...
    },
}
```

### Filtres ignorés

**Cause :** Erreur de syntaxe dans le filtre.

**Solution :** Vérifiez les logs pour les warnings de filtre invalide.

---

## Voir Aussi

- [Webhooks](./webhooks.md) - Alternative pour l'intégration système-à-système
- [Configuration](../graphql/configuration.md) - Paramètres subscription_settings
- [Permissions](../security/permissions.md) - Contrôle d'accès aux subscriptions
