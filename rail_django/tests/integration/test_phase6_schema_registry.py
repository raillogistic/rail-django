"""
Integration tests for schema snapshot export and diff endpoints.
"""

import json

import pytest
from django.test import Client as DjangoClient
from django.test import TestCase, override_settings

from rail_django.core.registry import schema_registry
from rail_django.core.schema import clear_all_schemas

pytestmark = pytest.mark.integration


@override_settings(
    RAIL_DJANGO_GRAPHQL={
        "schema_registry": {
            "enable_schema_snapshots": True,
            "enable_schema_export": True,
            "enable_schema_diff": True,
        }
    }
)
class TestSchemaRegistrySnapshots(TestCase):
    def setUp(self):
        schema_registry.clear()
        clear_all_schemas()
        schema_registry.register_schema(
            name="default",
            description="Default schema",
            apps=["tests"],
            auto_discover=False,
            settings={"schema_settings": {"authentication_required": False}},
        )
        self.client = DjangoClient()
        builder = schema_registry.get_schema_builder("default")
        builder.get_schema()
        self.builder = builder

    def test_schema_export_json(self):
        response = self.client.get("/api/v1/schemas/default/export/?format=json")
        assert response.status_code == 200
        payload = json.loads(response.content)
        data = payload.get("data", {})
        assert data.get("schema_name") == "default"
        assert isinstance(data.get("schema"), dict)

    def test_schema_history_and_diff(self):
        self.builder.rebuild_schema()

        history_response = self.client.get(
            "/api/v1/schemas/default/history/?limit=5"
        )
        assert history_response.status_code == 200
        history_payload = json.loads(history_response.content)
        history_data = history_payload.get("data", {})
        assert history_data.get("count", 0) >= 1

        diff_response = self.client.get("/api/v1/schemas/default/diff/")
        assert diff_response.status_code == 200
        diff_payload = json.loads(diff_response.content)
        diff_data = diff_payload.get("data", {})
        assert diff_data.get("schema_name") == "default"
        assert isinstance(diff_data.get("diff"), dict)
