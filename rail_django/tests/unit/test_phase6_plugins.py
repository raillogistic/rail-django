"""
Unit tests for plugin execution hooks.
"""

import graphene
import pytest

from rail_django.core.middleware import PluginMiddleware
from rail_django.plugins.base import BasePlugin, ExecutionHookResult, plugin_manager
from rail_django.testing import RailGraphQLTestClient, override_rail_settings

pytestmark = pytest.mark.unit


class InterceptPlugin(BasePlugin):
    def get_name(self) -> str:
        return "InterceptPlugin"

    def before_operation(self, schema_name, operation_type, operation_name, info, context):
        return ExecutionHookResult(handled=True, result="intercepted")


def test_plugin_middleware_can_intercept_operation():
    class Query(graphene.ObjectType):
        ping = graphene.String()

        def resolve_ping(root, info):
            return "pong"

    schema = graphene.Schema(query=Query)
    client = RailGraphQLTestClient(schema, schema_name="plugins")

    plugin = InterceptPlugin({"enabled": True})
    original_plugins = dict(plugin_manager._plugins)
    original_loaded = plugin_manager._loaded
    plugin_manager._plugins = {"InterceptPlugin": plugin}
    plugin_manager._loaded = True

    try:
        with override_rail_settings(
            global_settings={"plugin_settings": {"enable_execution_hooks": True}}
        ):
            result = client.execute(
                "{ ping }",
                middleware=[PluginMiddleware("plugins")],
            )
    finally:
        plugin_manager._plugins = original_plugins
        plugin_manager._loaded = original_loaded

    assert result["data"]["ping"] == "intercepted"

