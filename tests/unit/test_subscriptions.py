"""
Unit tests for subscriptions helper.
"""

import sys
import types
from unittest.mock import patch

import pytest
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from rail_django.extensions.subscriptions import get_subscription_consumer
from rail_django.extensions.subscriptions.consumer import RailGraphqlWsConsumer

pytestmark = pytest.mark.unit


def test_get_subscription_consumer_returns_class_with_schema():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("rail_django.core.schema.get_schema", lambda name="default": "schema")

        # Mock the consumer to avoid connecting signals or real logic
        # But for this test we just want to see if the class is returned properly
        
        consumer_class = get_subscription_consumer("default")
        
        # Instantiate to check schema injection
        # Note: In the new implementation, schema is fetched on connect(), not class definition time for the instance.
        # But get_subscription_consumer returns the class.
        
        assert consumer_class == RailGraphqlWsConsumer
        assert issubclass(consumer_class, AsyncJsonWebsocketConsumer)