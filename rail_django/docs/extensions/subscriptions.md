# GraphQL subscriptions extension

Rail Django supports real-time GraphQL subscriptions via WebSocket, allowing clients to receive instant updates when data changes in the system.

## Overview

The subscription system is built on top of **Django Channels** and provides:
- Automatic generation of CRUD events for your models.
- Advanced event filtering using the same syntax as queries.
- Granular permission control.
- Integration with major GraphQL clients like Apollo and Relay.

## Installation

Subscriptions require Django Channels and a channel layer (like Redis).

```bash
# Install with optional subscription dependencies
pip install rail-django[subscriptions]

# Or install manually
pip install channels channels-redis daphne
```

## Configuration

### 1. Enable Subscriptions
Enable and configure the subscription generator in your settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "subscription_settings": {
        "enable_subscriptions": True,
        # Auto-generate events for these operations
        "enable_create": True,
        "enable_update": True,
        "enable_delete": True,

        # Enable Prisma-style filters on subscriptions
        "enable_filters": True,

        # Model discovery
        "discover_models": True,
        "exclude_models": ["audit.AuditEvent"],
    },
}

# Configure Channel Layers (Redis recommended)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("localhost", 6379)],
        },
    },
}
```

### 2. Setup ASGI
You must configure your Django project to use ASGI for WebSocket support.

```python
# asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from rail_django.extensions.subscriptions import get_subscription_consumer

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_project.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter([
            path("graphql/", get_subscription_consumer()),
        ])
    ),
})
```

## Generated Subscriptions

For each registered model, Rail Django can generate the following subscriptions:

| Event | Subscription Name | Description |
|-------|-------------------|-------------|
| Created | `<model>Created` | Notifies when a new instance is created. |
| Updated | `<model>Updated` | Notifies when an instance is modified. |
| Deleted | `<model>Deleted` | Notifies when an instance is removed. |
| Changed | `<model>Changed` | Notifies on any of the above events. |

### Example Usage
```graphql
subscription OnOrderCreated {
  orderCreated(filters: { status: { eq: "pending" } }) {
    event # "created"
    timestamp
    node {
      id
      reference
      total
    }
  }
}
```

## Event Filtering

Rail Django supports advanced filtering on subscriptions, allowing clients to subscribe only to relevant events.

```graphql
subscription SpecificOrders {
  # Only notify for high-value orders from a specific customer
  orderChanged(filters: {
    AND: [
      { total: { gte: 1000 } },
      { customer: { id: { eq: "Cust_1" } } }
    ]
  }) {
    event
    node {
      reference
    }
  }
}
```

## Custom Subscriptions

You can define custom subscriptions by registering them in your schema.

```python
import graphene
from rail_django.core.registry import register_subscription

class MySubscription(graphene.ObjectType):
    custom_event = graphene.String()

    async def subscribe_custom_event(root, info):
        # Return the list of channel groups to subscribe to
        return ["custom_notifications"]

register_subscription(MySubscription)
```

To broadcast to this subscription:
```python
from rail_django.extensions.subscriptions import broadcast
broadcast("custom_notifications", {"custom_event": "Hello World!"})
```

## Permissions and Security

Subscriptions respect the same permission rules as queries and mutations. You can also define subscription-specific permissions in `GraphQLMeta`:

```python
class Order(models.Model):
    class GraphQLMeta:
        subscription_permissions = {
            "created": {"roles": ["sales", "admin"]},
            "deleted": {"roles": ["admin"]},
        }
```

## Apollo Client Integration

To use subscriptions with Apollo Client, use `split` to route subscription requests over WebSocket:

```typescript
import { split, HttpLink } from '@apollo/client';
import { WebSocketLink } from '@apollo/client/link/ws';
import { getMainDefinition } from '@apollo/client/utilities';

const httpLink = new HttpLink({ uri: '/graphql/' });
const wsLink = new WebSocketLink({
  uri: `ws://${window.location.host}/graphql/`,
  options: { reconnect: true }
});

const splitLink = split(
  ({ query }) => {
    const definition = getMainDefinition(query);
    return (
      definition.kind === 'OperationDefinition' &&
      definition.operation === 'subscription'
    );
  },
  wsLink,
  httpLink,
);
```

## See Also

- [Webhooks](./webhooks.md) - For server-to-server event notifications.
- [Permissions](../security/permissions.md) - For authorization details.
- [Production Deployment](../operations/deployment.md) - For ASGI server setup.
