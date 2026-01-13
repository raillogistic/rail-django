"""
Unit tests for the subscription generator.
"""

import sys
import types
from unittest.mock import patch

import pytest
from django.test import TestCase
from test_app.models import Category

from rail_django.core.settings import SubscriptionGeneratorSettings
from rail_django.generators.subscriptions import SubscriptionGenerator
from rail_django.generators.types import TypeGenerator
from rail_django.subscriptions.registry import (
    clear_subscription_registry,
    iter_subscriptions_for_model,
)

pytestmark = pytest.mark.unit


class TestSubscriptionGenerator(TestCase):
    def setUp(self):
        clear_subscription_registry()

    def test_generator_requires_dependency_when_enabled(self):
        settings = SubscriptionGeneratorSettings(enable_subscriptions=True)
        generator = SubscriptionGenerator(TypeGenerator(), settings=settings)

        original_import = __import__

        def _guarded_import(name, *args, **kwargs):
            if name == "channels_graphql_ws":
                raise ImportError("missing")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_guarded_import):
            with pytest.raises(ImportError):
                generator.generate_model_subscriptions(Category)

    def test_generator_registers_subscription_fields(self):
        class DummySubscriptionBase:
            SKIP = object()

            @classmethod
            def broadcast(cls, *args, **kwargs):
                return None

        dummy_module = types.SimpleNamespace(Subscription=DummySubscriptionBase)

        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(sys.modules, "channels_graphql_ws", dummy_module)
            settings = SubscriptionGeneratorSettings(enable_subscriptions=True)
            generator = SubscriptionGenerator(TypeGenerator(), settings=settings)
            fields = generator.generate_model_subscriptions(Category)

        assert "category_created" in fields
        assert "category_updated" in fields
        assert "category_deleted" in fields

        field_args = fields["category_created"].args
        assert "filters" in field_args

        subscriptions = list(iter_subscriptions_for_model(Category, "created"))
        assert subscriptions
