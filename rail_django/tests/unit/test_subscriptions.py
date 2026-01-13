"""
Unit tests for subscriptions helper.
"""

import sys
import types
from unittest.mock import patch

import pytest

from rail_django.extensions.subscriptions import get_subscription_consumer

pytestmark = pytest.mark.unit


def test_get_subscription_consumer_raises_when_dependency_missing():
    original_import = __import__

    def _guarded_import(name, *args, **kwargs):
        if name == "channels_graphql_ws":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_guarded_import):
        with pytest.raises(ImportError):
            get_subscription_consumer()


def test_get_subscription_consumer_returns_class_with_schema():
    dummy_module = types.SimpleNamespace(GraphqlWsConsumer=type("Base", (), {}))

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "channels_graphql_ws", dummy_module)
        mp.setattr("rail_django.core.schema.get_schema", lambda name="default": "schema")

        consumer = get_subscription_consumer("default")

    assert hasattr(consumer, "schema")
    assert consumer.schema == "schema"

