
from unittest.mock import MagicMock, patch
from django.db import models
from django.test import TestCase, override_settings
from rail_django.extensions.metadata import utils
from rail_django.extensions.metadata.extractor import ModelSchemaExtractor

class CacheTestModel(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = 'test_metadata_v2_cache'

class TestMetadataCaching(TestCase):
    def setUp(self):
        self.user = MagicMock()
        self.user.pk = 123
        self.user.is_authenticated = True

        # Reset cache-related mocks if needed, but we'll patch them per test

    @override_settings(DEBUG=False)
    @patch('rail_django.extensions.metadata.utils.cache')
    def test_get_cached_schema_debug_false(self, mock_cache):
        """Test retrieving from cache when DEBUG is False."""
        # Setup mock returns: version, static payload, dynamic overlay
        mock_cache.get.side_effect = [
            "12345",
            {"app": "app", "model": "model", "fields": []},
            {"permissions": {"can_list": True}, "mutations": [], "templates": []},
        ]

        result = utils.get_cached_schema("app", "model", user_id="123")

        self.assertEqual(result["app"], "app")
        self.assertIn("permissions", result)
        # Should be called 3 times: version + static + overlay
        self.assertEqual(mock_cache.get.call_count, 3)

    @override_settings(DEBUG=True)
    @patch('rail_django.extensions.metadata.utils.cache')
    def test_get_cached_schema_debug_true(self, mock_cache):
        """Test retrieving from cache is skipped when DEBUG is True."""
        result = utils.get_cached_schema("app", "model", user_id="123")

        self.assertIsNone(result)
        mock_cache.get.assert_not_called()

    @override_settings(DEBUG=False)
    @patch('rail_django.extensions.metadata.utils.cache')
    def test_set_cached_schema(self, mock_cache):
        """Test setting cache."""
        # Setup mock for version retrieval
        mock_cache.get.return_value = "12345"

        data = {"some": "data"}
        utils.set_cached_schema("app", "model", data, user_id="123")

        # Verify set was called for the schema
        # Note: might be called for version if not found, but we mocked get to return it

        # We look for the calls that set static + overlay payloads
        set_calls = mock_cache.set.call_args_list
        static_call = next((call for call in set_calls if "metadata_static:12345:app:model" in call[0][0]), None)
        overlay_call = next((call for call in set_calls if "metadata_overlay:12345:app:model" in call[0][0]), None)

        self.assertIsNotNone(static_call)
        self.assertIsNotNone(overlay_call)

    @override_settings(DEBUG=False)
    @patch('rail_django.extensions.metadata.utils.cache')
    @patch('rail_django.extensions.metadata.extractor.apps.get_model')
    @patch('rail_django.extensions.metadata.extractor.get_model_graphql_meta')
    def test_extractor_uses_cache(self, mock_get_meta, mock_get_model, mock_cache):
        """Test that extractor uses the cache."""
        mock_cache.get.side_effect = [
            "12345",
            {"app": "app", "model": "model", "fields": [], "metadata_version": "12345"},
            {"permissions": {}, "mutations": [], "templates": []},
        ]

        extractor = ModelSchemaExtractor()

        # Should return cached value and NOT call get_model
        result = extractor.extract("app", "model", user=self.user)

        self.assertEqual(result["app"], "app")
        self.assertEqual(result["model"], "model")
        mock_get_model.assert_not_called()

    @override_settings(DEBUG=False)
    @patch('rail_django.extensions.metadata.utils.cache')
    @patch('rail_django.extensions.metadata.extractor.apps.get_model')
    @patch('rail_django.extensions.metadata.extractor.get_model_graphql_meta')
    def test_extractor_populates_cache(self, mock_get_meta, mock_get_model, mock_cache):
        """Test that extractor populates cache on miss."""
        mock_cache.get.return_value = None # Cache miss

        mock_model = CacheTestModel
        mock_get_model.return_value = mock_model
        mock_get_meta.return_value = MagicMock()

        # We need to mock the mixin methods to return empty dicts/lists to avoid errors
        # or just rely on them working with our simple model.
        # Since CacheTestModel is real, it should work if we mock the mixins or let them run.
        # Let's mock the mixin methods to simplify the test.

        extractor = ModelSchemaExtractor()
        extractor._extract_fields = MagicMock(return_value=[])
        extractor._extract_relationships = MagicMock(return_value=[])
        extractor._extract_filters = MagicMock(return_value=[])
        extractor._extract_filter_config = MagicMock(return_value={})
        extractor._extract_relation_filters = MagicMock(return_value=[])
        extractor._extract_mutations = MagicMock(return_value=[])
        extractor._extract_permissions = MagicMock(return_value={})
        extractor._extract_field_groups = MagicMock(return_value=[])
        extractor._extract_templates = MagicMock(return_value=[])

        result = extractor.extract("test_metadata_v2_cache", "CacheTestModel", user=self.user)

        self.assertEqual(result['model'], "CacheTestModel")

        # Verify cache.set was called
        mock_cache.set.assert_called()

    @override_settings(DEBUG=False)
    @patch('rail_django.extensions.metadata.utils.cache')
    def test_invalidate_cache(self, mock_cache):
        """Test cache invalidation bumps version."""
        # Setup initial version
        mock_cache.get.side_effect = ["1000", None] # get version, get schema

        utils.invalidate_metadata_cache("app", "model")

        # Should set new version
        mock_cache.set.assert_called()
        args, _ = mock_cache.set.call_args
        self.assertIn("metadata_version:app:model", args[0])

    @override_settings(DEBUG=False)
    @patch('rail_django.extensions.metadata.utils.cache')
    @patch('rail_django.extensions.metadata.extractor.apps.get_model')
    @patch('rail_django.extensions.metadata.extractor.get_model_graphql_meta')
    def test_extractor_returns_dynamic_version(self, mock_get_meta, mock_get_model, mock_cache):
        """Test that extractor returns the dynamic version from cache."""
        # Mock cache to return a specific version
        def get_side_effect(key):
            if "metadata_version" in key:
                return "dynamic_version_123"
            return None
        mock_cache.get.side_effect = get_side_effect

        mock_model = CacheTestModel
        mock_get_model.return_value = mock_model
        mock_get_meta.return_value = MagicMock()

        extractor = ModelSchemaExtractor()
        # Mock mixins to avoid errors
        extractor._extract_fields = MagicMock(return_value=[])
        extractor._extract_relationships = MagicMock(return_value=[])
        extractor._extract_filters = MagicMock(return_value=[])
        extractor._extract_filter_config = MagicMock(return_value={})
        extractor._extract_relation_filters = MagicMock(return_value=[])
        extractor._extract_mutations = MagicMock(return_value=[])
        extractor._extract_permissions = MagicMock(return_value={})
        extractor._extract_field_groups = MagicMock(return_value=[])
        extractor._extract_templates = MagicMock(return_value=[])

        result = extractor.extract("app", "model", user=self.user)

        self.assertEqual(result['metadata_version'], "dynamic_version_123")
