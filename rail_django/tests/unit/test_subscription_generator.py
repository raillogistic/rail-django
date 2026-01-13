"""
Unit tests for the subscription generator.
"""

import sys
import types
from unittest.mock import patch

import pytest
import graphene
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
        class DummySubscriptionBase(graphene.ObjectType):
            SKIP = object()

            @classmethod
            def broadcast(cls, *args, **kwargs):
                return None

            @classmethod
            def Field(
                cls,
                name=None,
                description=None,
                deprecation_reason=None,
                required=False,
            ):
                from graphene.types.argument import to_arguments
                from graphene.utils.props import props

                arguments = {}
                args_class = getattr(cls, "Arguments", None)
                if args_class is not None:
                    arguments = props(args_class)

                return graphene.Field(
                    cls,
                    args=to_arguments(arguments),
                    name=name,
                    description=description,
                    deprecation_reason=deprecation_reason,
                    required=required,
                )

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

    def test_generator_respects_model_filters(self):
        class DummySubscriptionBase(graphene.ObjectType):
            SKIP = object()

            @classmethod
            def broadcast(cls, *args, **kwargs):
                return None

            @classmethod
            def Field(
                cls,
                name=None,
                description=None,
                deprecation_reason=None,
                required=False,
            ):
                from graphene.types.argument import to_arguments
                from graphene.utils.props import props

                arguments = {}
                args_class = getattr(cls, "Arguments", None)
                if args_class is not None:
                    arguments = props(args_class)

                return graphene.Field(
                    cls,
                    args=to_arguments(arguments),
                    name=name,
                    description=description,
                    deprecation_reason=deprecation_reason,
                    required=required,
                )

        dummy_module = types.SimpleNamespace(Subscription=DummySubscriptionBase)

        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(sys.modules, "channels_graphql_ws", dummy_module)
            settings = SubscriptionGeneratorSettings(
                enable_subscriptions=True,
                include_models=["OtherModel"],
            )
            generator = SubscriptionGenerator(TypeGenerator(), settings=settings)
            fields = generator.generate_model_subscriptions(Category)

        assert fields == {}

        with pytest.MonkeyPatch.context() as mp:
            mp.setitem(sys.modules, "channels_graphql_ws", dummy_module)
            settings = SubscriptionGeneratorSettings(
                enable_subscriptions=True,
                include_models=["Category"],
                exclude_models=["Category"],
            )
            generator = SubscriptionGenerator(TypeGenerator(), settings=settings)
            fields = generator.generate_model_subscriptions(Category)

        assert fields == {}
