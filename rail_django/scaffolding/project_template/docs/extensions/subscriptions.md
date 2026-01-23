# GraphQL Subscriptions

## Overview

Rail Django supports real-time GraphQL subscriptions via WebSocket. This guide covers configuration, generated subscriptions, event filtering, and production deployment.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Configuration](#configuration)
3. [ASGI Configuration](#asgi-configuration)
4. [Generated Subscriptions](#generated-subscriptions)
5. [Event Filtering](#event-filtering)
6. [Permissions and Security](#permissions-and-security)
7. [Per-Model Configuration](#per-model-configuration)
8. [Apollo Client Integration](#apollo-client-integration)
9. [Production Deployment](#production-deployment)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- **Django Channels** for WebSocket support
- **Redis** (recommended) for channel layer
- **ASGI server** (Daphne, Uvicorn)

### Installation

```bash
pip install channels channels-redis
```

---

## Configuration

### Basic Configuration

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "subscription_settings": {
        # Enable subscription generation
        "enable_subscriptions": True,

        # Event types
        "enable_create": True,
        "enable_update": True,
        "enable_delete": True,

        # Enable filters on subscriptions
        "enable_filters": True,

        # Model allowlist/blocklist
        "discover_models": False,  # Enable automatic model discovery
    "include_models": [],      # List of models to include
        "exclude_models": ["audit.AuditEvent"],
    },
}

# Channel Layers
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("localhost", 6379)],
        },
    },
}
```

---

## ASGI Configuration

### asgi.py

```python
# root/asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "root.settings.production")

# Import after Django setup
django_asgi_app = get_asgi_application()

from rail_django.subscriptions import GraphQLWebsocketConsumer

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter([
            path("graphql/ws/", GraphQLWebsocketConsumer.as_asgi()),
        ])
    ),
})
```

---

## Generated Subscriptions

### Naming Convention

For each model, Rail Django generates:

| Subscription | Format            | Description          |
| ------------ | ----------------- | -------------------- |
| Created      | `<model>Created`  | Listen for creations |
| Updated      | `<model>Updated`  | Listen for updates   |
| Deleted      | `<model>Deleted`  | Listen for deletions |
| All events   | `<model>Changed`  | All events           |

**Example for the `Order` model:**

```graphql
type Subscription {
  orderCreated(filters: OrderSubscriptionFilter): OrderSubscriptionPayload
  orderUpdated(filters: OrderSubscriptionFilter): OrderSubscriptionPayload
  orderDeleted(filters: OrderSubscriptionFilter): OrderSubscriptionPayload
  orderChanged(filters: OrderSubscriptionFilter): OrderSubscriptionPayload
}
```

### Payload Structure

```graphql
type OrderSubscriptionPayload {
  event: String! # "created", "updated", "deleted"
  node: OrderType # The object (null for delete)
  previous: OrderType # Previous values (for update)
  changedFields: [String] # Modified fields
  timestamp: DateTime!
  user: UserType # User who made the change
}
```

### Usage Example

```graphql
subscription OnOrderCreated {
  orderCreated {
    event
    node {
      id
      reference
      status
      total
      customer {
        name
      }
    }
    timestamp
    user {
      username
    }
  }
}
```

---

## Event Filtering

### Filter by Field

```graphql
subscription OrdersByStatus {
  orderUpdated(filters: { status: { eq: "pending" } }) {
    event
    node {
      id
      status
    }
  }
}
```

### Available Operators

| Operator    | Example                              |
| ----------- | ------------------------------------ |
| `eq`        | `status: { eq: "pending" }`          |
| `in`        | `status: { in: ["pending", "new"] }` |
| `contains`  | `name: { contains: "urgent" }`       |
| `gt`, `gte` | `total: { gte: 1000 }`               |
| `lt`, `lte` | `total: { lt: 100 }`                 |

### Filter by Relationship

```graphql
subscription CustomerOrders($customerId: ID!) {
  orderCreated(filters: { customer: { id: { eq: $customerId } } }) {
    node {
      id
      reference
    }
  }
}
```

### Combined Filters

```graphql
subscription HighValuePendingOrders {
  orderChanged(
    filters: {
      AND: [{ status: { eq: "pending" } }, { total: { gte: 1000 } }]
    }
  ) {
    event
    node {
      id
      total
    }
  }
}
```

---

## Permissions and Security

### JWT Authentication

```python
# root/asgi.py
from rail_django.subscriptions import JWTAuthMiddleware

application = ProtocolTypeRouter({
    "websocket": JWTAuthMiddleware(
        URLRouter([
            path("graphql/ws/", GraphQLWebsocketConsumer.as_asgi()),
        ])
    ),
})
```

### Client-Side Connection

```javascript
const wsLink = new WebSocketLink({
  uri: "wss://example.com/graphql/ws/",
  options: {
    connectionParams: {
      authorization: `Bearer ${accessToken}`,
    },
  },
});
```

### Per-Subscription Permissions

```python
class Order(models.Model):
    class GraphQLMeta:
        subscription_permissions = {
            "created": {"roles": ["sales", "admin"]},
            "updated": {"roles": ["sales", "admin"]},
            "deleted": {"roles": ["admin"]},
        }
```

---

## Per-Model Configuration

### GraphQLMeta Configuration

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Order(models.Model):
    """
    Order Model with subscription configuration.
    """
    reference = models.CharField(max_length=50)
    status = models.CharField(max_length=20)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    class GraphQLMeta(GraphQLMetaConfig):
        # ─── Subscription Configuration ───
        subscriptions = GraphQLMetaConfig.Subscriptions(
            # Enable for this model
            enabled=True,

            # Enabled events
            events=["created", "updated"],  # exclude "deleted"

            # Allowed filter fields
            filter_fields=["status", "customerId", "total"],

            # Fields included in payload
            payload_fields=["id", "reference", "status", "total"],

            # Exclude sensitive fields
            exclude_fields=["internalNotes"],
        )
```

### Disable for a Model

```python
class InternalLog(models.Model):
    class GraphQLMeta:
        subscriptions = GraphQLMetaConfig.Subscriptions(
            enabled=False,
        )
```

---

## Apollo Client Integration

### Client Configuration

```typescript
import { ApolloClient, InMemoryCache, HttpLink, split } from "@apollo/client";
import { WebSocketLink } from "@apollo/client/link/ws";
import { getMainDefinition } from "@apollo/client/utilities";

// HTTP link for queries and mutations
const httpLink = new HttpLink({
  uri: "/graphql/gql/",
});

// WebSocket link for subscriptions
const wsLink = new WebSocketLink({
  uri: `wss://${window.location.host}/graphql/ws/`,
  options: {
    reconnect: true,
    connectionParams: () => ({
      authorization: `Bearer ${localStorage.getItem("access_token")}`,
    }),
  },
});

// Split between HTTP and WebSocket
const splitLink = split(
  ({ query }) => {
    const definition = getMainDefinition(query);
    return (
      definition.kind === "OperationDefinition" &&
      definition.operation === "subscription"
    );
  },
  wsLink,
  httpLink,
);

export const client = new ApolloClient({
  link: splitLink,
  cache: new InMemoryCache(),
});
```

### React Component

```tsx
import { useSubscription, gql } from "@apollo/client";

const ORDER_SUBSCRIPTION = gql`
  subscription OnOrderCreated {
    orderCreated {
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
  const { data, loading, error } = useSubscription(ORDER_SUBSCRIPTION);

  if (loading) return <p>Listening for orders...</p>;
  if (error) return <p>Subscription error: {error.message}</p>;

  if (data) {
    const { node } = data.orderCreated;
    return (
      <div className="notification">
        New order: {node.reference} - ${node.total}
      </div>
    );
  }

  return null;
}
```

---

## Production Deployment

### Redis Channel Layer

```python
# root/settings/production.py
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [os.environ.get("REDIS_URL", "redis://localhost:6379/0")],
            "capacity": 1500,
            "expiry": 10,
        },
    },
}
```

### Daphne (ASGI Server)

```bash
# Install
pip install daphne

# Run
daphne -b 0.0.0.0 -p 8000 root.asgi:application
```

### Uvicorn

```bash
# Install
pip install uvicorn

# Run
uvicorn root.asgi:application --host 0.0.0.0 --port 8000 --workers 4
```

### Nginx Configuration

```nginx
# WebSocket support
location /graphql/ws/ {
    proxy_pass http://django;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 86400;
}
```

---

## Troubleshooting

### Connection Refused

**Cause:** ASGI server not running or port blocked.

**Solution:**

```bash
# Check if server is listening
netstat -tlnp | grep 8000

# Check firewall
sudo ufw allow 8000
```

### Authentication Failed

**Cause:** JWT token not passed or invalid.

**Solution:**

```javascript
// Verify connectionParams
const wsLink = new WebSocketLink({
  options: {
    connectionParams: () => {
      const token = localStorage.getItem("access_token");
      console.log("Token:", token); // Debug
      return { authorization: `Bearer ${token}` };
    },
  },
});
```

### No Events Received

**Cause:** Channel layer not configured or Redis unavailable.

**Solution:**

```python
# Test channel layer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

channel_layer = get_channel_layer()
async_to_sync(channel_layer.send)("test", {"type": "test.message"})
```

### Connection Drops

**Cause:** Nginx timeout or network issues.

**Solution:**

```nginx
# Increase timeouts
proxy_read_timeout 86400;
proxy_send_timeout 86400;
```

---

## See Also

- [Webhooks](./webhooks.md) - Event-based integration
- [Configuration](../graphql/configuration.md) - subscription_settings
- [Production Deployment](../deployment/production.md) - ASGI server setup
