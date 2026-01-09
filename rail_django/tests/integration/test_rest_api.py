"""
Integration tests for GraphQL schema management REST API.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from rail_django.core.registry import SchemaInfo, schema_registry
from rail_django.plugins.base import plugin_manager


class SchemaAPITestCase(TestCase):
    """Base test case for schema API tests."""

    def setUp(self):
        """Set up test environment."""
        self.client = Client()
        self.maxDiff = None

        # Clear registry before each test
        schema_registry.clear()

        # Create test user
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

    def tearDown(self):
        """Clean up after each test."""
        schema_registry.clear()

    def create_test_schema(self, name="test_schema", enabled=True):
        """Helper method to create a test schema."""
        return schema_registry.register_schema(
            name=name,
            description=f"Test schema: {name}",
            version="1.0.0",
            apps=["test_app"],
            models=["TestModel"],
            exclude_models=[],
            settings={"test": True},
            auto_discover=True,
            enabled=enabled,
        )


class SchemaListAPIViewTest(SchemaAPITestCase):
    """Tests for SchemaListAPIView."""

    def test_get_empty_schema_list(self):
        """Test getting empty schema list."""
        response = self.client.get("/api/v1/schemas/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"]["total_count"], 0)
        self.assertEqual(data["data"]["enabled_count"], 0)
        self.assertEqual(data["data"]["disabled_count"], 0)
        self.assertEqual(len(data["data"]["schemas"]), 0)

    def test_get_schema_list_summary(self):
        """Test getting schema list in summary format."""
        # Create test schemas
        self.create_test_schema("schema1", enabled=True)
        self.create_test_schema("schema2", enabled=False)

        response = self.client.get("/api/v1/schemas/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"]["total_count"], 2)
        self.assertEqual(data["data"]["enabled_count"], 1)
        self.assertEqual(data["data"]["disabled_count"], 1)

        schemas = data["data"]["schemas"]
        self.assertEqual(len(schemas), 2)

        # Check summary format
        schema1 = next(s for s in schemas if s["name"] == "schema1")
        self.assertEqual(schema1["enabled"], True)
        self.assertEqual(schema1["apps_count"], 1)
        self.assertEqual(schema1["models_count"], 1)
        self.assertNotIn("apps", schema1)  # Should not include detailed info

    def test_get_schema_list_detailed(self):
        """Test getting schema list in detailed format."""
        self.create_test_schema("schema1")

        response = self.client.get("/api/v1/schemas/?format=detailed")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        schemas = data["data"]["schemas"]
        self.assertEqual(len(schemas), 1)

        schema = schemas[0]
        self.assertEqual(schema["name"], "schema1")
        self.assertEqual(schema["apps"], ["test_app"])
        self.assertEqual(schema["models"], ["TestModel"])
        self.assertEqual(schema["settings"], {"test": True})

    def test_get_schema_list_with_filters(self):
        """Test filtering schema list."""
        self.create_test_schema("schema1", enabled=True)
        self.create_test_schema("schema2", enabled=False)

        # Filter by enabled status
        response = self.client.get("/api/v1/schemas/?enabled=true")
        data = response.json()
        self.assertEqual(len(data["data"]["schemas"]), 1)
        self.assertEqual(data["data"]["schemas"][0]["name"], "schema1")

        # Filter by disabled status
        response = self.client.get("/api/v1/schemas/?enabled=false")
        data = response.json()
        self.assertEqual(len(data["data"]["schemas"]), 1)
        self.assertEqual(data["data"]["schemas"][0]["name"], "schema2")

        # Filter by app
        response = self.client.get("/api/v1/schemas/?app=test_app")
        data = response.json()
        self.assertEqual(len(data["data"]["schemas"]), 2)

    def test_post_create_schema(self):
        """Test creating a new schema via POST."""
        schema_data = {
            "name": "new_schema",
            "description": "A new test schema",
            "version": "2.0.0",
            "apps": ["app1", "app2"],
            "models": ["Model1", "Model2"],
            "exclude_models": ["ExcludedModel"],
            "settings": {"custom": "value"},
            "auto_discover": False,
            "enabled": True,
        }

        response = self.client.post(
            "/api/v1/schemas/",
            data=json.dumps(schema_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()

        self.assertEqual(data["status"], "success")
        self.assertIn(
            "Schema 'new_schema' registered successfully", data["data"]["message"]
        )

        # Verify schema was created
        schema_info = schema_registry.get_schema("new_schema")
        self.assertIsNotNone(schema_info)
        self.assertEqual(schema_info.description, "A new test schema")
        self.assertEqual(schema_info.version, "2.0.0")
        self.assertEqual(schema_info.apps, ["app1", "app2"])

    def test_post_create_schema_minimal(self):
        """Test creating schema with minimal data."""
        schema_data = {"name": "minimal_schema"}

        response = self.client.post(
            "/api/v1/schemas/",
            data=json.dumps(schema_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        # Verify schema was created with defaults
        schema_info = schema_registry.get_schema("minimal_schema")
        self.assertIsNotNone(schema_info)
        self.assertEqual(schema_info.version, "1.0.0")
        self.assertEqual(schema_info.enabled, True)

    def test_post_create_schema_missing_name(self):
        """Test creating schema without name fails."""
        schema_data = {"description": "Schema without name"}

        response = self.client.post(
            "/api/v1/schemas/",
            data=json.dumps(schema_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertIn("Schema name is required", data["data"]["message"])

    def test_post_invalid_json(self):
        """Test POST with invalid JSON."""
        response = self.client.post(
            "/api/v1/schemas/", data="invalid json", content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertIn("Invalid JSON body", data["data"]["message"])


class SchemaDetailAPIViewTest(SchemaAPITestCase):
    """Tests for SchemaDetailAPIView."""

    def test_get_schema_detail(self):
        """Test getting detailed schema information."""
        self.create_test_schema("test_schema")

        response = self.client.get("/api/v1/schemas/test_schema/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        schema = data["data"]["schema"]
        self.assertEqual(schema["name"], "test_schema")
        self.assertEqual(schema["description"], "Test schema: test_schema")
        self.assertEqual(schema["version"], "1.0.0")
        self.assertEqual(schema["apps"], ["test_app"])
        self.assertEqual(schema["models"], ["TestModel"])
        self.assertEqual(schema["enabled"], True)
        self.assertIn("builder", schema)

    def test_get_nonexistent_schema(self):
        """Test getting nonexistent schema returns 404."""
        response = self.client.get("/api/v1/schemas/nonexistent/")

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertIn("Schema 'nonexistent' not found", data["data"]["message"])

    def test_put_update_schema(self):
        """Test updating schema via PUT."""
        self.create_test_schema("test_schema")

        update_data = {
            "description": "Updated description",
            "version": "2.0.0",
            "enabled": False,
        }

        response = self.client.put(
            "/api/v1/schemas/test_schema/",
            data=json.dumps(update_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(
            "Schema 'test_schema' updated successfully", data["data"]["message"]
        )

        # Verify update
        schema_info = schema_registry.get_schema("test_schema")
        self.assertEqual(schema_info.description, "Updated description")
        self.assertEqual(schema_info.version, "2.0.0")
        self.assertEqual(schema_info.enabled, False)

    def test_put_update_nonexistent_schema(self):
        """Test updating nonexistent schema returns 404."""
        update_data = {"description": "New description"}

        response = self.client.put(
            "/api/v1/schemas/nonexistent/",
            data=json.dumps(update_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("Schema 'nonexistent' not found", data["data"]["message"])

    def test_delete_schema(self):
        """Test deleting schema via DELETE."""
        self.create_test_schema("test_schema")

        response = self.client.delete("/api/v1/schemas/test_schema/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(
            "Schema 'test_schema' deleted successfully", data["data"]["message"]
        )

        # Verify deletion
        self.assertFalse(schema_registry.schema_exists("test_schema"))

    def test_delete_nonexistent_schema(self):
        """Test deleting nonexistent schema returns 404."""
        response = self.client.delete("/api/v1/schemas/nonexistent/")

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("Schema 'nonexistent' not found", data["data"]["message"])


class SchemaManagementAPIViewTest(SchemaAPITestCase):
    """Tests for SchemaManagementAPIView."""

    def test_enable_schema(self):
        """Test enabling a schema."""
        schema_info = self.create_test_schema("test_schema", enabled=False)

        response = self.client.post(
            "/api/v1/management/",
            data=json.dumps({"action": "enable", "schema_name": "test_schema"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(
            "Schema 'test_schema' enabled successfully", data["data"]["message"]
        )

        # Verify schema is enabled
        updated_schema = schema_registry.get_schema("test_schema")
        self.assertTrue(updated_schema.enabled)

    def test_disable_schema(self):
        """Test disabling a schema."""
        self.create_test_schema("test_schema", enabled=True)

        response = self.client.post(
            "/api/v1/management/",
            data=json.dumps({"action": "disable", "schema_name": "test_schema"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(
            "Schema 'test_schema' disabled successfully", data["data"]["message"]
        )

        # Verify schema is disabled
        updated_schema = schema_registry.get_schema("test_schema")
        self.assertFalse(updated_schema.enabled)

    def test_clear_all_schemas(self):
        """Test clearing all schemas."""
        self.create_test_schema("schema1")
        self.create_test_schema("schema2")

        response = self.client.post(
            "/api/v1/management/",
            data=json.dumps({"action": "clear_all"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("All schemas cleared successfully", data["data"]["message"])

        # Verify all schemas are cleared
        self.assertEqual(len(schema_registry.list_schemas()), 0)

    def test_unknown_action(self):
        """Test unknown management action returns error."""
        response = self.client.post(
            "/api/v1/management/",
            data=json.dumps({"action": "unknown_action"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Unknown action: unknown_action", data["data"]["message"])


class SchemaDiscoveryAPIViewTest(SchemaAPITestCase):
    """Tests for SchemaDiscoveryAPIView."""

    @patch.object(schema_registry, "auto_discover_schemas")
    def test_post_trigger_discovery(self, mock_discover):
        """Test triggering schema discovery."""
        mock_discover.return_value = 3

        response = self.client.post("/api/v1/discovery/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["data"]["discovered_count"], 3)
        self.assertIn("Schema discovery completed", data["data"]["message"])
        mock_discover.assert_called_once()

    def test_get_discovery_status(self):
        """Test getting discovery status."""
        self.create_test_schema("schema1", enabled=True)
        self.create_test_schema("schema2", enabled=False)

        response = self.client.get("/api/v1/discovery/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        discovery_data = data["data"]
        self.assertTrue(discovery_data["discovery_enabled"])
        self.assertEqual(discovery_data["total_schemas"], 2)
        self.assertEqual(
            discovery_data["auto_discover_schemas"], 2
        )  # Both have auto_discover=True


class SchemaHealthAPIViewTest(SchemaAPITestCase):
    """Tests for SchemaHealthAPIView."""

    def test_health_check_healthy(self):
        """Test health check with healthy status."""
        self.create_test_schema("schema1", enabled=True)
        self.create_test_schema("schema2", enabled=True)

        response = self.client.get("/api/v1/health/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        health_data = data["data"]
        self.assertEqual(health_data["status"], "healthy")
        self.assertEqual(health_data["total_schemas"], 2)
        self.assertEqual(health_data["enabled_schemas"], 2)
        self.assertEqual(health_data["disabled_schemas"], 0)
        self.assertTrue(health_data["registry_initialized"])
        self.assertEqual(len(health_data["issues"]), 0)

    def test_health_check_warning_no_enabled_schemas(self):
        """Test health check with warning when no enabled schemas."""
        self.create_test_schema("schema1", enabled=False)

        response = self.client.get("/api/v1/health/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        health_data = data["data"]
        self.assertEqual(health_data["status"], "warning")
        self.assertEqual(health_data["enabled_schemas"], 0)
        self.assertIn("No enabled schemas found", health_data["issues"])


class SchemaMetricsAPIViewTest(SchemaAPITestCase):
    """Tests for SchemaMetricsAPIView."""

    def test_get_metrics(self):
        """Test getting schema metrics."""
        # Create test schemas with different configurations
        schema_registry.register_schema(
            name="schema1",
            apps=["app1", "app2"],
            models=["Model1", "Model2"],
            version="1.0.0",
            enabled=True,
        )
        schema_registry.register_schema(
            name="schema2",
            apps=["app1"],
            models=["Model3"],
            exclude_models=["ExcludedModel"],
            version="2.0.0",
            enabled=False,
            auto_discover=False,
        )

        response = self.client.get("/api/v1/metrics/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        metrics = data["data"]["metrics"]
        self.assertEqual(metrics["total_schemas"], 2)
        self.assertEqual(metrics["enabled_schemas"], 1)
        self.assertEqual(metrics["disabled_schemas"], 1)
        self.assertEqual(metrics["auto_discover_schemas"], 1)
        self.assertEqual(metrics["total_models"], 3)
        self.assertEqual(metrics["total_excluded_models"], 1)

        # Check app distribution
        self.assertEqual(metrics["schemas_by_app"]["app1"], 2)
        self.assertEqual(metrics["schemas_by_app"]["app2"], 1)

        # Check version distribution
        self.assertEqual(metrics["schemas_by_version"]["1.0.0"], 1)
        self.assertEqual(metrics["schemas_by_version"]["2.0.0"], 1)

        # Check plugin metrics
        plugin_metrics = metrics["plugin_metrics"]
        self.assertIn("total_plugins", plugin_metrics)
        self.assertIn("enabled_plugins", plugin_metrics)
        self.assertIn("plugin_names", plugin_metrics)


class CORSTest(SchemaAPITestCase):
    """Tests for CORS functionality."""

    def test_cors_headers(self):
        """Test CORS headers are included in responses."""
        response = self.client.get("/api/v1/schemas/")

        self.assertEqual(response["Access-Control-Allow-Origin"], "*")
        self.assertEqual(
            response["Access-Control-Allow-Methods"], "GET, POST, PUT, DELETE, OPTIONS"
        )
        self.assertEqual(
            response["Access-Control-Allow-Headers"], "Content-Type, Authorization"
        )

    def test_options_request(self):
        """Test OPTIONS preflight request."""
        response = self.client.options("/api/v1/schemas/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")


class ErrorHandlingTest(SchemaAPITestCase):
    """Tests for error handling in API views."""

    @patch.object(schema_registry, "list_schemas")
    def test_internal_server_error(self, mock_list):
        """Test handling of internal server errors."""
        mock_list.side_effect = Exception("Database error")

        response = self.client.get("/api/v1/schemas/")

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertIn("Failed to list schemas", data["data"]["message"])

    def test_malformed_json(self):
        """Test handling of malformed JSON in POST requests."""
        response = self.client.post(
            "/api/v1/schemas/",
            data='{"invalid": json}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Invalid JSON body", data["data"]["message"])
