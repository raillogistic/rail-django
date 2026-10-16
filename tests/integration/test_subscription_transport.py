"""Transport regressions for generated, authorized WebSocket subscriptions."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import graphene
import pytest
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import override_settings
from django.urls import path
from channels.routing import URLRouter

from rail_django.core.settings import SubscriptionGeneratorSettings
from rail_django.extensions.subscriptions import get_subscription_consumer
from rail_django.extensions.subscriptions.registry import clear_subscription_registry
from rail_django.generators.subscriptions import SubscriptionGenerator
from rail_django.generators.types import TypeGenerator
from rail_django.testing import override_rail_settings
from test_app.models import Category

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_committed_events_rollback_revocation_and_group_cleanup():
    """Exercise a real ASGI route and in-memory channel layer."""
    user = get_user_model().objects.create_superuser(
        username="socket_owner", password="temporary"
    )
    settings = {
        "schema_settings": {"authentication_required": True},
        "security_settings": {"enable_abac": False},
    }
    with override_settings(
        CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    ):
        with override_rail_settings(schema_settings={"transport": settings}):
            generator = SubscriptionGenerator(
                TypeGenerator(schema_name="transport"),
                SubscriptionGeneratorSettings(
                    enable_subscriptions=True, discover_models=True
                ),
                schema_name="transport",
            )

            class Query(graphene.ObjectType):
                ping = graphene.String()

            subscription = type(
                "TransportSubscription",
                (graphene.ObjectType,),
                generator.generate_model_subscriptions(Category),
            )
            schema = graphene.Schema(query=Query, subscription=subscription)
            app = URLRouter(
                [path("graphql/", get_subscription_consumer("transport").as_asgi())]
            )

            def create(name, rollback=False):
                with transaction.atomic():
                    obj = Category.objects.create(name=name)
                    if rollback:
                        transaction.set_rollback(True)
                    return obj.pk

            async def scenario():
                socket = WebsocketCommunicator(
                    app, "/graphql/", subprotocols=["graphql-transport-ws"]
                )
                socket.scope["user"] = user
                assert (await socket.connect())[0]
                await socket.send_json_to({"type": "connection_init"})
                assert (await socket.receive_json_from())["type"] == "connection_ack"
                query = "subscription { categoryCreated { id event node { name } } }"
                for op in ("1", "2"):
                    await socket.send_json_to(
                        {"type": "subscribe", "id": op, "payload": {"query": query}}
                    )
                # Ping acknowledgement is ordered after registration on this connection.
                await socket.send_json_to({"type": "ping"})
                ack = await socket.receive_json_from()
                assert ack["type"] == "pong", ack
                pk = await database_sync_to_async(create)("Committed")
                messages = [
                    await socket.receive_json_from(),
                    await socket.receive_json_from(),
                ]
                assert {m["id"] for m in messages} == {"1", "2"}
                for message in messages:
                    assert message["type"] == "next"
                    assert message["payload"]["data"]["categoryCreated"] == {
                        "id": str(pk),
                        "event": "created",
                        "node": {"name": "Committed"},
                    }
                await socket.send_json_to({"type": "complete", "id": "1"})
                await socket.send_json_to({"type": "ping"})
                assert (await socket.receive_json_from())["type"] == "pong"
                await database_sync_to_async(create)("Rolled back", rollback=True)
                assert await socket.receive_nothing(timeout=0.05)
                await database_sync_to_async(create)("Still subscribed")
                assert (await socket.receive_json_from())["id"] == "2"
                # A fresh user is loaded for every publication, invalidating Django's permission cache.
                await database_sync_to_async(
                    lambda: get_user_model()
                    .objects.filter(pk=user.pk)
                    .update(is_superuser=False)
                )()
                await database_sync_to_async(create)("Denied after revocation")
                assert await socket.receive_nothing(timeout=0.05)
                await socket.disconnect()
                assert not get_channel_layer().groups

            with patch(
                "rail_django.extensions.subscriptions.consumer.get_schema",
                return_value=schema,
            ):
                try:
                    async_to_sync(scenario)()
                finally:
                    clear_subscription_registry("transport")


def test_transport_rejects_queries_and_subscribe_before_init():
    class Query(graphene.ObjectType):
        ping = graphene.String()

    schema = graphene.Schema(query=Query)
    app = get_subscription_consumer("transport").as_asgi()

    async def scenario():
        socket = WebsocketCommunicator(app, "/", subprotocols=["graphql-transport-ws"])
        assert (await socket.connect())[0]
        await socket.send_json_to(
            {"type": "subscribe", "id": "1", "payload": {"query": "{ ping }"}}
        )
        assert (await socket.receive_output())["code"] == 4401
        await socket.disconnect()
        socket = WebsocketCommunicator(app, "/", subprotocols=["graphql-transport-ws"])
        assert (await socket.connect())[0]
        await socket.send_json_to({"type": "connection_init"})
        await socket.receive_json_from()
        await socket.send_json_to(
            {"type": "subscribe", "id": "1", "payload": {"query": "{ ping }"}}
        )
        assert (await socket.receive_json_from())["type"] == "error"
        await socket.disconnect()

    with patch(
        "rail_django.extensions.subscriptions.consumer.get_schema", return_value=schema
    ):
        async_to_sync(scenario)()


@pytest.mark.parametrize(
    "message",
    [
        {"type": "connection_init", "payload": []},
        {"type": "connection_init", "payload": {"Authorization": 123}},
        {"type": "complete", "id": []},
        {"type": "complete"},
    ],
)
def test_transport_rejects_malformed_envelopes(message):
    class Query(graphene.ObjectType):
        ping = graphene.String()

    schema = graphene.Schema(query=Query)
    app = get_subscription_consumer("transport").as_asgi()

    async def scenario():
        socket = WebsocketCommunicator(app, "/", subprotocols=["graphql-transport-ws"])
        assert (await socket.connect())[0]
        await socket.send_json_to(message)
        assert (await socket.receive_output())["code"] == 4400
        await socket.disconnect()

    with patch(
        "rail_django.extensions.subscriptions.consumer.get_schema", return_value=schema
    ):
        async_to_sync(scenario)()


def test_tenant_delivery_and_deleted_snapshot():
    from tests.models import TenantOrganization, TenantProject

    user = get_user_model().objects.create_superuser(
        username="tenant-socket", password="temporary"
    )
    a = TenantOrganization.objects.create(name="A")
    b = TenantOrganization.objects.create(name="B")
    config = {
        "tenant_transport": {
            "security_settings": {"enable_abac": False},
            "multitenancy_settings": {
                "enabled": True,
                "default_tenant_field": "organization",
                "allow_cross_tenant_superuser": False,
            },
        }
    }
    with override_settings(
        CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    ):
        with override_rail_settings(schema_settings=config):
            generator = SubscriptionGenerator(
                TypeGenerator(schema_name="tenant_transport"),
                SubscriptionGeneratorSettings(
                    enable_subscriptions=True, discover_models=True
                ),
                schema_name="tenant_transport",
            )

            class Query(graphene.ObjectType):
                ping = graphene.String()

            subscription = type(
                "TenantTransportSubscription",
                (graphene.ObjectType,),
                generator.generate_model_subscriptions(TenantProject),
            )
            schema = graphene.Schema(query=Query, subscription=subscription)
            app = get_subscription_consumer("tenant_transport").as_asgi()

            async def scenario():
                sockets = []
                try:
                    for tenant in (a, b):
                        socket = WebsocketCommunicator(
                            app, "/", subprotocols=["graphql-transport-ws"]
                        )
                        socket.scope.update(user=user, tenant_id=tenant.pk)
                        assert (await socket.connect())[0]
                        sockets.append(socket)
                        await socket.send_json_to({"type": "connection_init"})
                        await socket.receive_json_from()
                        for event in ("Created", "Deleted"):
                            await socket.send_json_to(
                                {
                                    "type": "subscribe",
                                    "id": event,
                                    "payload": {
                                        "query": f"subscription {{ tenantproject{event} {{ id }} }}"
                                    },
                                }
                            )
                        await socket.send_json_to({"type": "ping"})
                        ack = await socket.receive_json_from()
                        assert ack["type"] == "pong", ack
                    obj = await database_sync_to_async(TenantProject.objects.create)(
                        name="Private to A", organization=a
                    )
                    message = await sockets[0].receive_json_from()
                    assert message["payload"]["data"]["tenantprojectCreated"][
                        "id"
                    ] == str(obj.pk)
                    assert await sockets[1].receive_nothing(timeout=0.05)
                    pk = obj.pk
                    await database_sync_to_async(obj.delete)()
                    message = await sockets[0].receive_json_from()
                    assert message["payload"]["data"]["tenantprojectDeleted"][
                        "id"
                    ] == str(pk)
                    assert await sockets[1].receive_nothing(timeout=0.05)
                finally:
                    for socket in sockets:
                        await socket.disconnect()

            with patch(
                "rail_django.extensions.subscriptions.consumer.get_schema",
                return_value=schema,
            ):
                try:
                    async_to_sync(scenario)()
                finally:
                    clear_subscription_registry("tenant_transport")
