"""
Optional GraphQL subscriptions integration for Django Channels.

This module is intentionally lightweight and only works when
channels_graphql_ws is installed.
"""

from __future__ import annotations

from typing import Any


def get_subscription_consumer(schema_name: str = "default") -> Any:
    """
    Return a Channels consumer class for GraphQL subscriptions.

    Usage:
        from rail_django.extensions.subscriptions import get_subscription_consumer
        application = ProtocolTypeRouter({
            "websocket": URLRouter([
                path("graphql/", get_subscription_consumer()),
            ])
        })
    """
    try:
        import channels_graphql_ws  # type: ignore
    except Exception as exc:
        raise ImportError(
            "channels-graphql-ws is required for subscriptions. "
            "Install it with: pip install channels-graphql-ws"
        ) from exc

    from ..core.schema import get_schema

    class RailGraphqlWsConsumer(channels_graphql_ws.GraphqlWsConsumer):
        schema = get_schema(schema_name)

        async def on_connect(self, payload):
            self.scope["schema_name"] = schema_name
            self.user = self.scope.get("user")
            await super().on_connect(payload)

    as_asgi = getattr(RailGraphqlWsConsumer, "as_asgi", None)
    if callable(as_asgi):
        return RailGraphqlWsConsumer.as_asgi()
    return RailGraphqlWsConsumer
