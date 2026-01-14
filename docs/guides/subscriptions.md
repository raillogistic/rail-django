# Subscriptions

This document describes the subscription system built into Rail Django.

## Overview

Subscriptions are auto-generated per model for create/update/delete events.
They use Django Channels and `channels-graphql-ws`.

Event flow:

- Django `post_save` and `post_delete` signals fire.
- Events are broadcast to Channels groups.
- GraphQL subscription resolvers publish `event`, `node`, and `id`.

## Requirements

Dependencies:

- `channels`
- `daphne`
- `channels-graphql-ws`

The helper `rail_django.extensions.subscriptions.get_subscription_consumer`
raises `ImportError` when `channels-graphql-ws` is not installed.

## Configuration

Enable subscriptions in settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "subscription_settings": {
        "enable_subscriptions": True,
        "enable_create": True,
        "enable_update": True,
        "enable_delete": True,
        "enable_filters": True,
        "include_models": ["shop.Order"],
        "exclude_models": ["audit.AuditEvent"],
    },
}
```

Allowlist subscription fields (optional):

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "subscription_field_allowlist": ["order_created", "order_updated"],
    }
}
```

## Model-specific Configuration

You can configure subscriptions per-model using `GraphQLMeta`:

```python
class Project(models.Model):
    # ... fields ...

    class GraphQLMeta:
        # Enable all events
        subscriptions = True
        
        # Or specify allowed events
        # subscriptions = ["create", "update"]
        
        # Or use a dictionary for granular control
        # subscriptions = {"create": True, "delete": False}
```

This overrides the global `enable_create`, `enable_update`, etc. settings for that specific model.

## ASGI wiring

```python
# settings.py
INSTALLED_APPS = [
    "daphne",
    "channels",
    # ...
]

ASGI_APPLICATION = "root.asgi.application"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}
```

```python
# root/asgi.py
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import path
from rail_django.extensions.subscriptions import get_subscription_consumer

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter([
        path("graphql/", get_subscription_consumer("gql")),
    ]),
})
```

## Generated fields and payload

For each model, fields are generated using this pattern:

- `<model>_created`
- `<model>_updated`
- `<model>_deleted`

Payload shape:

```graphql
subscription {
  order_created {
    event
    id
    node { id status total }
  }
}
```

Response fields:

- `event`: `created`, `updated`, or `deleted`
- `id`: model primary key
- `node`: the model instance

## Client example (Apollo)

```tsx
import { ApolloClient, InMemoryCache, HttpLink, split } from "@apollo/client";
import { WebSocketLink } from "@apollo/client/link/ws";
import { getMainDefinition } from "@apollo/client/utilities";

const httpLink = new HttpLink({ uri: "/graphql/gql/" });
const wsLink = new WebSocketLink({
  uri: "ws://localhost:8000/graphql/",
  options: { reconnect: true },
});

const link = split(
  ({ query }) => {
    const def = getMainDefinition(query);
    return def.kind === "OperationDefinition" && def.operation === "subscription";
  },
  wsLink,
  httpLink
);

export const client = new ApolloClient({
  link,
  cache: new InMemoryCache(),
});
```

## Filtering

If `enable_filters` is true, subscriptions accept a `filters` argument with the
same operators as list queries. Filters are evaluated:

- In the DB for create/update events.
- In-memory for delete events (fallback when DB lookup is not possible).

Invalid filters are ignored and the event is skipped.

## Permissions and masking

Subscriptions respect:

- `schema_settings.authentication_required`
- `GraphQLMeta` access checks for `list`, `retrieve`, and `subscribe`
- Field-level masking for non-superusers

If authentication or permissions fail, the event is skipped.

## Broadcasting details

Signals are wired via `rail_django.subscriptions.broadcaster` and deliver to
group names built as:

```
rail_sub:<schema_name>:<model_label>:<event>
```

Groups are sanitized and truncated if needed.

## Failure behavior

- Missing `channels-graphql-ws`: import error during consumer creation.
- Filter errors: event is skipped and a warning is logged.
- Permission or auth errors: event is skipped.
