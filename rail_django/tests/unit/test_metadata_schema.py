"""
Test suite for the GraphQL metadata schema functionality.

This module tests the ModelMetadataQuery and related components to ensure
proper exposure of Django model metadata with appropriate permission filtering.
"""

from unittest.mock import MagicMock, Mock, patch

import graphene
import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.test import TestCase, override_settings
from graphql import GraphQLError
from rail_django.testing import RailGraphQLTestClient

from rail_django.core.settings import SchemaSettings
from rail_django.extensions.metadata import (
    FieldMetadataType,
    ModelMetadataExtractor,
    ModelMetadataQuery,
    ModelMetadataType,
    RelationshipMetadataType,
)
import rail_django.extensions.metadata as metadata_module


class MetadataTestModel(models.Model):
    """Test model for metadata extraction testing."""

    name = models.CharField(max_length=100, help_text="Name of the test item")
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "test_app"
        permissions = [
            ("view_metadatatestmodel_name", "Can view test model name"),
            ("view_metadatatestmodel_description", "Can view test model description"),
        ]


class RelatedTestModel(models.Model):
    """Related test model for relationship testing."""

    test_item = models.ForeignKey(
        MetadataTestModel, on_delete=models.CASCADE, related_name="related_items"
    )
    value = models.IntegerField()

    class Meta:
        app_label = "test_app"


class ParentModel(models.Model):
    """Parent model for polymorphic table metadata tests."""

    name = models.CharField(max_length=50)

    class Meta:
        app_label = "test_app"


class TagModel(models.Model):
    """Tag model for ManyToMany polymorphic table metadata tests."""

    label = models.CharField(max_length=50)

    class Meta:
        app_label = "test_app"


class PolymorphicChildModel(ParentModel):
    """Child model with OneToOne and ManyToMany relations."""

    partner = models.OneToOneField(
        "self", on_delete=models.CASCADE, null=True, blank=True
    )
    tags = models.ManyToManyField(TagModel, related_name="children")

    class Meta:
        app_label = "test_app"


class TestModelMetadataExtractor(TestCase):
    """Test cases for ModelMetadataExtractor class."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.extractor = ModelMetadataExtractor()

    def test_extract_field_metadata_basic(self):
        """Test basic field metadata extraction."""
        field = MetadataTestModel._meta.get_field("name")
        metadata = self.extractor._extract_field_metadata(field, self.user)

        self.assertEqual(metadata.name, "name")
        self.assertEqual(metadata.field_type, "CharField")
        self.assertEqual(metadata.max_length, 100)
        self.assertEqual(metadata.help_text, "Name of the test item")
        self.assertFalse(metadata.null)
        self.assertFalse(metadata.blank)
        self.assertTrue(metadata.has_permission)

    def test_extract_field_metadata_with_permissions(self):
        """Test field metadata extraction with specific permissions."""
        # Create permission for viewing name field
        content_type = ContentType.objects.get_for_model(MetadataTestModel)
        permission, _ = Permission.objects.get_or_create(
            codename="view_metadatatestmodel_name",
            name="Can view test model name",
            content_type=content_type,
        )
        self.user.user_permissions.add(permission)

        field = MetadataTestModel._meta.get_field("name")
        metadata = self.extractor._extract_field_metadata(field, self.user)

        self.assertTrue(metadata.has_permission)

    def test_extract_field_metadata_without_permissions(self):
        """Test field metadata extraction without specific permissions."""
        field = MetadataTestModel._meta.get_field("description")
        metadata = self.extractor._extract_field_metadata(field, self.user)

        # Should still have permission if no specific permission is required
        self.assertTrue(metadata.has_permission)

    def test_extract_relationship_metadata(self):
        """Test relationship metadata extraction."""
        field = RelatedTestModel._meta.get_field("test_item")
        metadata = self.extractor._extract_relationship_metadata(field, self.user)

        self.assertEqual(metadata.name, "test_item")
        self.assertEqual(metadata.relationship_type, "ForeignKey")
        self.assertEqual(metadata.related_model, "MetadataTestModel")
        self.assertEqual(metadata.related_app, "test_app")
        self.assertTrue(metadata.has_permission)

    @patch("rail_django.extensions.metadata.apps.get_model")
    def test_extract_model_metadata_complete(self, mock_get_model):
        """Test complete model metadata extraction."""
        mock_get_model.return_value = MetadataTestModel

        metadata = self.extractor.extract_model_metadata(
            app_name="test_app",
            model_name="MetadataTestModel",
            user=self.user,
            nested_fields=True,
            permissions_included=True,
        )

        self.assertEqual(metadata.app_name, "test_app")
        self.assertEqual(metadata.model_name, "MetadataTestModel")
        self.assertIsNotNone(metadata.fields)
        self.assertIsNotNone(metadata.relationships)
        self.assertTrue(len(metadata.fields) > 0)

    @patch("rail_django.extensions.metadata.apps.get_model")
    def test_extract_model_metadata_no_nested_fields(self, mock_get_model):
        """Test model metadata extraction without nested fields."""
        mock_get_model.return_value = TestModel

        metadata = self.extractor.extract_model_metadata(
            app_name="test_app",
            model_name="TestModel",
            user=self.user,
            nested_fields=False,
            permissions_included=True,
        )

        self.assertEqual(len(metadata.relationships), 0)

    @patch("rail_django.extensions.metadata.apps.get_model")
    def test_extract_model_metadata_invalid_model(self, mock_get_model):
        """Test model metadata extraction with invalid model."""
        mock_get_model.side_effect = LookupError("Model not found")

        metadata = self.extractor.extract_model_metadata(
            app_name="invalid_app",
            model_name="InvalidModel",
            user=self.user,
            nested_fields=True,
            permissions_included=True,
        )

        self.assertIsNone(metadata)


class TestModelMetadataQuery(TestCase):
    """Test cases for ModelMetadataQuery GraphQL resolver."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.query = ModelMetadataQuery()

    @patch("rail_django.extensions.metadata.get_core_schema_settings")
    @patch(
        "rail_django.extensions.metadata.ModelMetadataExtractor.extract_model_metadata"
    )
    def test_resolve_model_metadata_success(self, mock_extract, mock_get_settings):
        """Test successful model metadata resolution."""
        # Mock settings to allow metadata exposure
        mock_settings = Mock()
        mock_settings.show_metadata = True
        mock_get_settings.return_value = mock_settings

        # Mock extracted metadata
        mock_metadata = Mock()
        mock_metadata.app_name = "test_app"
        mock_metadata.model_name = "TestModel"
        mock_extract.return_value = mock_metadata

        # Mock GraphQL info object
        info = Mock()
        info.context = Mock()
        info.context.user = self.user

        result = self.query.resolve_model_metadata(
            info,
            app_name="test_app",
            model_name="TestModel",
            nested_fields=True,
            permissions_included=True,
        )

        self.assertEqual(result, mock_metadata)
        mock_extract.assert_called_once_with(
            app_name="test_app",
            model_name="TestModel",
            user=self.user,
            nested_fields=True,
            permissions_included=True,
            include_filters=True,
            include_mutations=True,
        )

    @patch("rail_django.extensions.metadata.get_core_schema_settings")
    def test_resolve_model_metadata_disabled(self, mock_get_settings):
        """Test model metadata resolution when disabled in settings."""
        # Mock settings to disable metadata exposure
        mock_settings = Mock()
        mock_settings.show_metadata = False
        mock_get_settings.return_value = mock_settings

        # Mock GraphQL info object
        info = Mock()
        info.context = Mock()
        info.context.user = self.user

        with self.assertRaises(GraphQLError):
            self.query.resolve_model_metadata(
                info, app_name="test_app", model_name="TestModel"
            )

    @patch("rail_django.extensions.metadata.get_core_schema_settings")
    def test_resolve_model_metadata_no_user(self, mock_get_settings):
        """Test model metadata resolution without authenticated user."""
        # Mock settings to allow metadata exposure
        mock_settings = Mock()
        mock_settings.show_metadata = True
        mock_get_settings.return_value = mock_settings

        # Mock GraphQL info object without user
        info = Mock()
        info.context = Mock()
        info.context.user = None

        with self.assertRaises(GraphQLError):
            self.query.resolve_model_metadata(
                info, app_name="test_app", model_name="TestModel"
            )

    @patch("rail_django.extensions.metadata.get_core_schema_settings")
    @patch(
        "rail_django.extensions.metadata.ModelMetadataExtractor.extract_model_metadata"
    )
    def test_resolve_model_metadata_extraction_error(
        self, mock_extract, mock_get_settings
    ):
        """Test model metadata resolution with extraction error."""
        # Mock settings to allow metadata exposure
        mock_settings = Mock()
        mock_settings.show_metadata = True
        mock_get_settings.return_value = mock_settings

        # Mock extraction to return None (error case)
        mock_extract.return_value = None

        # Mock GraphQL info object
        info = Mock()
        info.context = Mock()
        info.context.user = self.user

        with self.assertRaises(GraphQLError):
            self.query.resolve_model_metadata(
                info, app_name="invalid_app", model_name="InvalidModel"
            )


class TestGraphQLIntegration(TestCase):
    """Integration tests for GraphQL schema with metadata queries."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")

    @patch("rail_django.extensions.metadata.get_core_schema_settings")
    @patch("rail_django.extensions.metadata.apps.get_model")
    def test_graphql_query_execution(self, mock_get_model, mock_get_settings):
        """Test GraphQL query execution for model metadata."""
        # Mock settings to allow metadata exposure
        mock_settings = Mock()
        mock_settings.show_metadata = True
        mock_get_settings.return_value = mock_settings

        # Mock model
        mock_get_model.return_value = TestModel

        # Create GraphQL schema with metadata query
        class Query(ModelMetadataQuery, graphene.ObjectType):
            pass

        schema = graphene.Schema(query=Query)
        client = RailGraphQLTestClient(schema, schema_name="test", user=self.user)

        # Execute GraphQL query
        query = """
        query {
            modelMetadata(
                appName: "test_app",
                modelName: "TestModel",
                nestedFields: true,
                permissionsIncluded: true
            ) {
                appName
                modelName
                fields {
                    name
                    fieldType
                    hasPermission
                }
                relationships {
                    name
                    relationshipType
                    relatedModel
                }
            }
        }
        """

        result = client.execute(query)

        # Verify no errors in execution
        self.assertIsNone(result.get("errors"))

        # Verify data structure
        data = result.get("data", {})
        metadata = data.get("modelMetadata")
        if metadata:  # Only check if metadata was returned
            self.assertEqual(metadata["appName"], "test_app")
            self.assertEqual(metadata["modelName"], "TestModel")
            self.assertIsInstance(metadata["fields"], list)
            self.assertIsInstance(metadata["relationships"], list)


class TestPermissionFiltering(TestCase):
    """Test cases for permission-based field filtering."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.extractor = ModelMetadataExtractor()

    def test_field_permission_checking(self):
        """Test field-level permission checking."""
        # Create specific field permission
        content_type = ContentType.objects.get_for_model(TestModel)
        permission, _ = Permission.objects.get_or_create(
            codename="view_testmodel_name",
            name="Can view test model name",
            content_type=content_type,
        )

        # Test without permission
        field = TestModel._meta.get_field("name")
        metadata_without_perm = self.extractor._extract_field_metadata(field, self.user)

        # Add permission to user
        self.user.user_permissions.add(permission)

        # Test with permission
        metadata_with_perm = self.extractor._extract_field_metadata(field, self.user)

        # Both should have permission in this implementation
        # (adjust based on actual permission logic)
        self.assertTrue(metadata_with_perm.has_permission)

    @patch("rail_django.extensions.metadata.apps.get_model")
    def test_model_metadata_permission_filtering(self, mock_get_model):
        """Test that model metadata respects permission filtering."""
        mock_get_model.return_value = TestModel

        metadata = self.extractor.extract_model_metadata(
            app_name="test_app",
            model_name="TestModel",
            user=self.user,
            nested_fields=True,
            permissions_included=True,
        )

        # Verify that permission information is included
        if metadata and metadata.fields:
            for field in metadata.fields:
                self.assertIsNotNone(field.has_permission)


class TestEdgeCases(TestCase):
    """Test cases for edge cases and error conditions."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.extractor = ModelMetadataExtractor()

    @patch("rail_django.extensions.metadata.apps.get_model")
    def test_nonexistent_model(self, mock_get_model):
        """Test handling of nonexistent model."""
        mock_get_model.side_effect = LookupError("Model not found")

        metadata = self.extractor.extract_model_metadata(
            app_name="nonexistent_app",
            model_name="NonexistentModel",
            user=self.user,
            nested_fields=True,
            permissions_included=True,
        )

        self.assertIsNone(metadata)

    def test_anonymous_user(self):
        """Test handling of anonymous user."""
        from django.contrib.auth.models import AnonymousUser

        anonymous_user = AnonymousUser()
        field = TestModel._meta.get_field("name")
        metadata = self.extractor._extract_field_metadata(field, anonymous_user)

        # Should handle anonymous user gracefully
        self.assertIsNotNone(metadata)

    @patch("rail_django.extensions.metadata.get_core_schema_settings")
    def test_missing_schema_settings(self, mock_get_settings):
        """Test handling when schema settings are missing."""
        mock_get_settings.return_value = None

        query = ModelMetadataQuery()
        info = Mock()
        info.context = Mock()
        info.context.user = self.user

        with self.assertRaises(GraphQLError):
            query.resolve_model_metadata(
                info, app_name="test_app", model_name="TestModel"
            )


class TestMetadataAccessGating(TestCase):
    """Test access gating for metadata resolvers."""

    def setUp(self):
        self.query = ModelMetadataQuery()

    @patch("rail_django.extensions.metadata.get_core_schema_settings")
    def test_resolve_available_models_requires_auth(self, mock_get_settings):
        mock_settings = Mock()
        mock_settings.show_metadata = True
        mock_get_settings.return_value = mock_settings

        info = Mock()
        info.context = Mock()
        info.context.user = None

        with self.assertRaises(GraphQLError):
            self.query.resolve_available_models(info)

    @patch("rail_django.extensions.metadata.get_core_schema_settings")
    def test_resolve_model_table_requires_auth(self, mock_get_settings):
        mock_settings = Mock()
        mock_settings.show_metadata = True
        mock_get_settings.return_value = mock_settings

        info = Mock()
        info.context = Mock()
        info.context.user = None

        with self.assertRaises(GraphQLError):
            self.query.resolve_model_table(
                info, app_name="test_app", model_name="TestModel"
            )

    @patch("rail_django.extensions.metadata.get_core_schema_settings")
    def test_resolve_model_form_metadata_requires_auth(self, mock_get_settings):
        mock_settings = Mock()
        mock_settings.show_metadata = True
        mock_get_settings.return_value = mock_settings

        info = Mock()
        info.context = Mock()
        info.context.user = None

        with self.assertRaises(GraphQLError):
            self.query.resolve_model_form_metadata(
                info, app_name="test_app", model_name="TestModel"
            )

    @patch("rail_django.extensions.metadata.get_core_schema_settings")
    def test_resolve_app_models_requires_auth(self, mock_get_settings):
        mock_settings = Mock()
        mock_settings.show_metadata = True
        mock_get_settings.return_value = mock_settings

        info = Mock()
        info.context = Mock()
        info.context.user = None

        with self.assertRaises(GraphQLError):
            self.query.resolve_app_models(info, app_name="test_app")


class TestMetadataCaching(TestCase):
    """Test caching settings and invalidation behavior."""

    def setUp(self):
        metadata_module._table_cache.clear()

    @override_settings(DEBUG=False, RAIL_DJANGO_GRAPHQL={"METADATA": {}})
    def test_table_cache_timeout_default_in_production(self):
        metadata_module._load_table_cache_policy()
        self.assertIsNone(metadata_module._get_table_cache_timeout())

    @override_settings(
        DEBUG=False,
        RAIL_DJANGO_GRAPHQL={"METADATA": {"table_cache_timeout_seconds": 120}},
    )
    def test_table_cache_timeout_respects_override(self):
        metadata_module._load_table_cache_policy()
        self.assertEqual(metadata_module._get_table_cache_timeout(), 120)

    @override_settings(
        DEBUG=False,
        RAIL_DJANGO_GRAPHQL={"METADATA": {"table_cache_enabled": False}},
    )
    def test_table_cache_disabled(self):
        user = User.objects.create_user(username="cacheuser", password="testpass")
        extractor = metadata_module.ModelTableExtractor()

        with patch("rail_django.extensions.metadata.apps.get_model") as mock_get_model:
            mock_get_model.return_value = TestModel
            extractor.extract_model_table_metadata(
                app_name="test_app",
                model_name="TestModel",
                user=user,
                include_filters=False,
                include_mutations=False,
                include_pdf_templates=False,
            )

        self.assertEqual(len(metadata_module._table_cache), 0)

    def test_invalidate_metadata_cache_removes_model_entries(self):
        cache_key = metadata_module._make_table_cache_key(
            "default",
            "test_app",
            "TestModel",
            False,
            exclude=[],
            only=[],
            include_nested=True,
            only_lookup=[],
            exclude_lookup=[],
            include_filters=True,
            include_mutations=True,
            include_templates=True,
        )
        metadata_module._table_cache[cache_key] = {
            "value": "value",
            "expires_at": None,
            "created_at": 0,
        }

        metadata_module.invalidate_metadata_cache(
            model_name="TestModel", app_name="test_app"
        )

        self.assertNotIn(cache_key, metadata_module._table_cache)

    @override_settings(
        DEBUG=False,
        RAIL_DJANGO_GRAPHQL={"METADATA": {"clear_cache_on_start": False}},
    )
    @patch("rail_django.extensions.metadata.invalidate_metadata_cache")
    def test_invalidate_cache_on_startup_respects_setting(self, mock_invalidate):
        metadata_module.invalidate_cache_on_startup()
        mock_invalidate.assert_not_called()

    @override_settings(
        DEBUG=False,
        RAIL_DJANGO_GRAPHQL={"METADATA": {"clear_cache_on_start": True}},
    )
    @patch("rail_django.extensions.metadata.invalidate_metadata_cache")
    def test_invalidate_cache_on_startup_runs(self, mock_invalidate):
        metadata_module.invalidate_cache_on_startup()
        mock_invalidate.assert_called_once()


class TestPolymorphicTableMetadata(TestCase):
    """Test polymorphic/multi-table edge cases for table metadata."""

    def setUp(self):
        self.user = User.objects.create_user(username="polyuser", password="testpass")
        self.extractor = metadata_module.ModelTableExtractor()

    @patch("rail_django.extensions.metadata.apps.get_model")
    def test_polymorphic_hides_one_to_one_fields(self, mock_get_model):
        mock_get_model.return_value = PolymorphicChildModel

        metadata = self.extractor.extract_model_table_metadata(
            app_name="test_app",
            model_name="PolymorphicChildModel",
            user=self.user,
            include_filters=False,
            include_mutations=False,
            include_pdf_templates=False,
        )

        field_names = {field.name for field in metadata.fields}
        self.assertNotIn("partner", field_names)
        self.assertIn("tags", field_names)


if __name__ == "__main__":
    pytest.main([__file__])
