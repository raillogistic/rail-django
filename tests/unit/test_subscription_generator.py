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
from rail_django.extensions.subscriptions.registry import (
    _SUBSCRIPTION_REGISTRY,
    clear_subscription_registry,
    iter_subscriptions_for_model,
)
from rail_django.generators.subscriptions.utils import RailSubscription

pytestmark = pytest.mark.unit


class TestSubscriptionGenerator(TestCase):
    def setUp(self):
        clear_subscription_registry()

    def test_generator_registers_subscription_fields(self):
        settings = SubscriptionGeneratorSettings(enable_subscriptions=True, discover_models=True)
        generator = SubscriptionGenerator(TypeGenerator(), settings=settings)
        fields = generator.generate_model_subscriptions(Category)

        assert "category_created" in fields
        assert "category_updated" in fields
        assert "category_deleted" in fields

        field = fields["category_created"]
        assert "filters" in field.args

        subscriptions = list(iter_subscriptions_for_model(Category, "created"))
        assert subscriptions
        
        # Verify it inherits from RailSubscription
        subscription_class = subscriptions[0][1]
        assert issubclass(subscription_class, RailSubscription)

    def test_generator_respects_model_filters(self):
        settings = SubscriptionGeneratorSettings(
            enable_subscriptions=True,
            include_models=["OtherModel"],
        )
        generator = SubscriptionGenerator(TypeGenerator(), settings=settings)
        fields = generator.generate_model_subscriptions(Category)

        assert fields == {}

        settings = SubscriptionGeneratorSettings(
            enable_subscriptions=True,
            include_models=["Category"],
            exclude_models=["Category"],
        )
        generator = SubscriptionGenerator(TypeGenerator(), settings=settings)
        fields = generator.generate_model_subscriptions(Category)

        assert fields == {}
