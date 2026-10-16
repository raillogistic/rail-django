"""GraphQL over WebSocket using the graphql-transport-ws protocol."""

import logging
from typing import Any
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from graphql import GraphQLError, OperationType, get_operation_ast, parse
from rail_django.core.schema import get_schema
from .protocol import GRAPHQL_TRANSPORT_WS_PROTOCOL

logger = logging.getLogger(__name__)


class RailGraphqlWsConsumer(AsyncJsonWebsocketConsumer):
    """Register groups separately from GraphQL publication serialization."""

    schema_name = "default"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._subscriptions = {}
        self._initialized = False
        self._token = None

    async def connect(self):
        self.schema_name = (
            self.scope.get("url_route", {})
            .get("kwargs", {})
            .get("schema_name", self.schema_name)
        )
        try:
            self.schema = await database_sync_to_async(get_schema)(self.schema_name)
        except Exception:
            await self.close(code=4400)
            return
        if GRAPHQL_TRANSPORT_WS_PROTOCOL not in self.scope.get("subprotocols", []):
            await self.close(code=4406)
            return
        await self.accept(subprotocol=GRAPHQL_TRANSPORT_WS_PROTOCOL)

    async def disconnect(self, code):
        for op_id in list(self._subscriptions):
            await self.unsubscribe(op_id)

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            await self.close(code=4400)
            return
        kind = content.get("type")
        if kind == "connection_init":
            if self._initialized:
                await self.close(code=4429)
                return
            params = content.get("payload")
            if params is None:
                params = {}
            if not isinstance(params, dict):
                await self.close(code=4400)
                return
            auth = params.get("Authorization", params.get("authorization", ""))
            if not isinstance(auth, str):
                await self.close(code=4400)
                return
            auth = (
                auth
                or dict(self.scope.get("headers", []))
                .get(b"authorization", b"")
                .decode()
            )
            if auth:
                if not auth.lower().startswith("bearer "):
                    await self.close(code=4403)
                    return
                self._token = auth.split(" ", 1)[1]
                if not await database_sync_to_async(self._authenticated_user)():
                    await self.close(code=4403)
                    return
            self._initialized = True
            await self.send_json({"type": "connection_ack"})
        elif kind == "ping":
            await self.send_json({"type": "pong", "payload": content.get("payload")})
        elif kind == "subscribe":
            if not self._initialized:
                await self.close(code=4401)
                return
            await self.handle_subscribe(content)
        elif kind == "complete":
            if not isinstance(content.get("id"), str) or not content["id"]:
                await self.close(code=4400)
                return
            await self.unsubscribe(content.get("id"))
        elif kind != "pong":
            await self.close(code=4400)

    def _authenticated_user(self):
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        if self._token:
            self._jwt_payload = {}
            from rail_django.extensions.auth import JWTManager

            payload = JWTManager.verify_token(self._token, expected_type="access")
            if not payload:
                return None
            self._jwt_payload = payload
            return user_model.objects.filter(
                pk=payload.get("user_id") or payload.get("sub"), is_active=True
            ).first()
        user = self.scope.get("user")
        if isinstance(user, user_model):
            return user_model.objects.filter(pk=user.pk, is_active=True).first()
        return user

    def _execute(self, params, *, publication=False, payload=None):
        if publication:
            self.schema = get_schema(self.schema_name)
        from django.http import HttpRequest

        context = HttpRequest()
        context.method = "POST"
        context.path = self.scope.get("path", "/graphql/")
        context.user = self._authenticated_user()
        context.schema_name = self.schema_name
        context.scope = self.scope
        context.is_subscription = not publication
        context.is_publication = publication
        context.subscription_groups = set()
        context.jwt_payload = getattr(self, "_jwt_payload", {})
        context.META = {
            "HTTP_" + key.decode().upper().replace("-", "_"): value.decode()
            for key, value in self.scope.get("headers", [])
        }
        if self.scope.get("tenant_id") is not None:
            context.tenant_id = self.scope["tenant_id"]
        from rail_django.core.middleware import get_middleware_stack

        result = self.schema.execute(
            params["query"],
            variable_values=params.get("variables"),
            operation_name=params.get("operationName"),
            context_value=context,
            root_value=payload,
            middleware=get_middleware_stack(self.schema_name),
        )
        return result, context.subscription_groups

    async def handle_subscribe(self, payload):
        op_id = payload.get("id")
        if not isinstance(op_id, str) or not op_id:
            await self.close(code=4400)
            return
        if op_id in self._subscriptions:
            await self.close(code=4409)
            return
        groups = set()
        try:
            if len(self._subscriptions) >= 100:
                raise GraphQLError("Too many subscriptions")
            params = payload.get("payload") or {}
            operation = get_operation_ast(
                parse(params["query"]), params.get("operationName")
            )
            if operation is None or operation.operation != OperationType.SUBSCRIPTION:
                raise GraphQLError("A subscription operation is required")
            result, groups = await database_sync_to_async(self._execute)(params)
            if result.errors:
                await self.send_json(
                    {
                        "type": "error",
                        "id": op_id,
                        "payload": [error.formatted for error in result.errors],
                    }
                )
                return
            if not groups:
                raise GraphQLError("No subscription groups registered")
            for group in groups:
                await self.channel_layer.group_add(group, self.channel_name)
            self._subscriptions[op_id] = {"groups": groups, "params": params}
        except Exception as exc:
            for group in groups:
                if not any(
                    group in op["groups"] for op in self._subscriptions.values()
                ):
                    await self.channel_layer.group_discard(group, self.channel_name)
            message = (
                str(exc) if isinstance(exc, GraphQLError) else "Subscription failed"
            )
            logger.debug("Subscription registration failed", exc_info=True)
            await self.send_json(
                {"type": "error", "id": op_id, "payload": [{"message": message}]}
            )

    async def unsubscribe(self, op_id):
        data = self._subscriptions.pop(op_id, None)
        if data:
            retained = set().union(
                *(op["groups"] for op in self._subscriptions.values())
            )
            for group in data["groups"] - retained:
                await self.channel_layer.group_discard(group, self.channel_name)

    async def graphql_subscription_broadcast(self, event):
        for op_id, data in list(self._subscriptions.items()):
            if event.get("group") not in data["groups"]:
                continue
            try:
                result, _ = await database_sync_to_async(self._execute)(
                    data["params"], publication=True, payload=event.get("payload")
                )
                if result.errors:
                    await self.send_json(
                        {
                            "type": "error",
                            "id": op_id,
                            "payload": [error.formatted for error in result.errors],
                        }
                    )
                    await self.unsubscribe(op_id)
                elif result.data and any(
                    value is not None for value in result.data.values()
                ):
                    await self.send_json(
                        {"type": "next", "id": op_id, "payload": {"data": result.data}}
                    )
            except Exception:
                logger.exception("Subscription publication failed")
                await self.unsubscribe(op_id)
                await self.send_json(
                    {
                        "type": "error",
                        "id": op_id,
                        "payload": [{"message": "Subscription failed"}],
                    }
                )


def get_subscription_consumer(schema_name: str = "default") -> Any:
    """Return a schema-bound consumer class; call .as_asgi() for routing."""
    if schema_name == "default":
        return RailGraphqlWsConsumer
    return type(
        "SchemaGraphqlWsConsumer",
        (RailGraphqlWsConsumer,),
        {"schema_name": schema_name},
    )
