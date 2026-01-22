# Subscriptions

Rail Django supports GraphQL subscriptions via `channels-graphql-ws`.

## Installation

You need to install the optional dependencies.

```bash
pip install rail-django[subscriptions]
# or
pip install channels channels-graphql-ws daphne
```

## Configuration

### 1. Enable Subscriptions

```python
# settings.py
RAIL_DJANGO_GRAPHQL = {
    "subscription_settings": {
        "enable_subscriptions": True,
        "enable_create": True, # Auto-generate create events
        "enable_update": True, # Auto-generate update events
        "enable_delete": True, # Auto-generate delete events
    }
}
```

### 2. Setup ASGI

You need to configure Django Channels.

```python
# asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from rail_django.subscriptions import MyGraphqlConsumer

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_project.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter([
        path("graphql/", MyGraphqlConsumer.as_asgi()),
    ]),
})
```

## Auto-Generated Events

If enabled, Rail Django automatically broadcasts events for your models.

```graphql
subscription {
  # Subscribe to all user updates
  userUpdated {
    user {
      id
      username
    }
  }
}
```

### Filtering Subscriptions

You can subscribe to specific events using filters.

```graphql
subscription {
  # Only notify when a user in the 'staff' group is updated
  userUpdated(filters: { isStaff: true }) {
    user {
      username
    }
  }
}
```

## Custom Subscriptions

You can register custom subscriptions in `schema.py`.

```python
import graphene
from rail_django.core.registry import register_subscription
import asyncio

class MySubscription(graphene.ObjectType):
    time_update = graphene.String()
    
    async def subscribe_time_update(root, info):
        # Return the group name to subscribe to (managed by Channels)
        return ["time_events"]

register_subscription(MySubscription)
```

### Broadcasting Events

To trigger the custom subscription from anywhere in your Django code:

```python
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

channel_layer = get_channel_layer()
async_to_sync(channel_layer.group_send)(
    "time_events",
    {
        "type": "broadcast", # Must match the handler in your consumer if custom
        "payload": {"time_update": "12:00 PM"}
    }
)
```
