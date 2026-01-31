
from django.db import models
from django.test import TestCase
import unittest.mock
from unittest.mock import MagicMock
from rail_django.extensions.metadata.extractor import ModelSchemaExtractor

class FieldNameTestModel(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    user_profile = models.ForeignKey('self', on_delete=models.CASCADE, null=True)

    class Meta:
        app_label = 'test_metadata_field_names'

class TestMetadataFieldNames(TestCase):
    def setUp(self):
        self.extractor = ModelSchemaExtractor()
        self.user = MagicMock()

    def test_field_names_extraction(self):
        """Test that fields have both 'name' (camelCase) and 'field_name' (original)."""
        fields = self.extractor._extract_fields(FieldNameTestModel, self.user)

        # Check first_name
        first_name_field = next((f for f in fields if f['field_name'] == 'first_name'), None)
        self.assertIsNotNone(first_name_field)
        self.assertEqual(first_name_field['name'], 'firstName')
        self.assertEqual(first_name_field['field_name'], 'first_name')

        # Check last_name
        last_name_field = next((f for f in fields if f['field_name'] == 'last_name'), None)
        self.assertIsNotNone(last_name_field)
        self.assertEqual(last_name_field['name'], 'lastName')
        self.assertEqual(last_name_field['field_name'], 'last_name')

    def test_relationship_names_extraction(self):
        """Test that relationships have both 'name' (camelCase) and 'field_name' (original)."""
        relationships = self.extractor._extract_relationships(FieldNameTestModel, self.user)

        # Check user_profile
        profile_rel = next((r for r in relationships if r['field_name'] == 'user_profile'), None)
        self.assertIsNotNone(profile_rel)
        self.assertEqual(profile_rel['name'], 'userProfile')
        self.assertEqual(profile_rel['field_name'], 'user_profile')

    def test_field_groups_camelcase(self):
        """Test that field groups fields are converted to camelCase."""
        with unittest.mock.patch('rail_django.extensions.metadata.extractor.get_model_graphql_meta') as mock_get_meta:
            mock_meta = MagicMock(custom_metadata=None)
            mock_meta.field_groups = [
                {
                    "key": "basics",
                    "label": "Basics",
                    "fields": ["first_name", "last_name"]
                }
            ]
            mock_get_meta.return_value = mock_meta

            # Use FieldNameTestModel (already defined in this file)
            with unittest.mock.patch('rail_django.extensions.metadata.extractor.apps.get_model') as mock_get_model:
                mock_get_model.return_value = FieldNameTestModel

                # Mock mixins
                self.extractor._extract_fields = MagicMock(return_value=[])
                self.extractor._extract_relationships = MagicMock(return_value=[])
                self.extractor._extract_filters = MagicMock(return_value=[])
                self.extractor._extract_filter_config = MagicMock(return_value={})
                self.extractor._extract_relation_filters = MagicMock(return_value=[])
                self.extractor._extract_mutations = MagicMock(return_value=[])
                self.extractor._extract_permissions = MagicMock(return_value={})
                self.extractor._extract_templates = MagicMock(return_value=[])

                result = self.extractor.extract('test_metadata_field_names', 'FieldNameTestModel', self.user)

                self.assertEqual(len(result['field_groups']), 1)
                self.assertEqual(result['field_groups'][0]['fields'], ['firstName', 'lastName'])


    def test_ordering_camelcase(self):
        """Test that ordering fields are converted to camelCase."""
        # Mock meta.ordering
        with unittest.mock.patch('rail_django.extensions.metadata.extractor.get_model_graphql_meta') as mock_get_meta:
            mock_get_meta.return_value = MagicMock(custom_metadata=None, field_groups=[])

            # Create a mock model with ordering
            class OrderedModel(models.Model):
                first_name = models.CharField(max_length=100)
                created_at = models.DateTimeField()

                class Meta:
                    app_label = 'test_ordering'
                    ordering = ['first_name', '-created_at']

            # We need to register this model or mock apps.get_model
            with unittest.mock.patch('rail_django.extensions.metadata.extractor.apps.get_model') as mock_get_model:
                mock_get_model.return_value = OrderedModel

                # Mock the extractors to return empty to focus on the main extract method logic
                self.extractor._extract_fields = MagicMock(return_value=[])
                self.extractor._extract_relationships = MagicMock(return_value=[])
                self.extractor._extract_filters = MagicMock(return_value=[])
                self.extractor._extract_filter_config = MagicMock(return_value={})
                self.extractor._extract_relation_filters = MagicMock(return_value=[])
                self.extractor._extract_mutations = MagicMock(return_value=[])
                self.extractor._extract_permissions = MagicMock(return_value={})
                self.extractor._extract_field_groups = MagicMock(return_value=[])
                self.extractor._extract_templates = MagicMock(return_value=[])

                result = self.extractor.extract('test_ordering', 'OrderedModel', self.user)

                self.assertEqual(result['ordering'], ['firstName', '-createdAt'])

    def test_unique_together_camelcase(self):
        """Test that unique_together fields are converted to camelCase."""
        with unittest.mock.patch('rail_django.extensions.metadata.extractor.get_model_graphql_meta') as mock_get_meta:
            mock_meta = MagicMock(custom_metadata=None, field_groups=[])
            mock_get_meta.return_value = mock_meta

            class UniqueModel(models.Model):
                first_name = models.CharField(max_length=100)
                last_name = models.CharField(max_length=100)

                class Meta:
                    app_label = 'test_unique'
                    unique_together = [['first_name', 'last_name']]

            with unittest.mock.patch('rail_django.extensions.metadata.extractor.apps.get_model') as mock_get_model:
                mock_get_model.return_value = UniqueModel

                # Mock mixins
                self.extractor._extract_fields = MagicMock(return_value=[])
                self.extractor._extract_relationships = MagicMock(return_value=[])
                self.extractor._extract_filters = MagicMock(return_value=[])
                self.extractor._extract_filter_config = MagicMock(return_value={})
                self.extractor._extract_relation_filters = MagicMock(return_value=[])
                self.extractor._extract_mutations = MagicMock(return_value=[])
                self.extractor._extract_permissions = MagicMock(return_value={})
                self.extractor._extract_templates = MagicMock(return_value=[])

                result = self.extractor.extract('test_unique', 'UniqueModel', self.user)

                self.assertEqual(len(result['unique_together']), 1)
                self.assertEqual(result['unique_together'][0], ['firstName', 'lastName'])

    def test_presets_naming(self):
        """Test that filter presets have correct name (camelCase) and preset_name (original)."""
        # Patch in filter_extractor because _extract_filter_config is defined there
        with unittest.mock.patch('rail_django.extensions.metadata.filter_extractor.get_model_graphql_meta') as mock_get_meta:
            mock_meta = MagicMock(custom_metadata=None, field_groups=[])
            mock_meta.filter_presets = {
                "active_users": {"status": "active"},
                "recent_items": {"created_at__gt": "2023-01-01"}
            }
            mock_get_meta.return_value = mock_meta

            with unittest.mock.patch('rail_django.extensions.metadata.extractor.apps.get_model') as mock_get_model:
                mock_get_model.return_value = FieldNameTestModel

                # Mock extractors
                self.extractor._extract_fields = MagicMock(return_value=[])
                self.extractor._extract_relationships = MagicMock(return_value=[])
                # We need _extract_filters to return something or just mock it
                self.extractor._extract_filters = MagicMock(return_value=[])
                # _extract_filter_config is what we are testing mostly, but it's called by extract
                # Wait, presets are part of filter_config.
                # But filter_config extraction logic is in FilterExtractorMixin._extract_filter_config
                # We need to make sure we are testing the result of extract() which calls _extract_filter_config

                # We can't easily mock _extract_filter_config if we want to test its logic.
                # So we should let it run.
                # But we need to mock what it depends on.
                # It depends on get_model_graphql_meta (mocked) and FilteringSettings (maybe).

                # Let's verify _extract_filter_config output directly or via extract
                # Since we didn't mock _extract_filter_config, it uses the real one from the mixin

                # Mock other unrelated mixins
                self.extractor._extract_relation_filters = MagicMock(return_value=[])
                self.extractor._extract_mutations = MagicMock(return_value=[])
                self.extractor._extract_permissions = MagicMock(return_value={})
                self.extractor._extract_field_groups = MagicMock(return_value=[])
                self.extractor._extract_templates = MagicMock(return_value=[])

                result = self.extractor.extract('test_metadata_field_names', 'FieldNameTestModel', self.user)

                config = result['filter_config']
                presets = config['presets']

                active_preset = next((p for p in presets if p['preset_name'] == 'active_users'), None)
                self.assertIsNotNone(active_preset)
                self.assertEqual(active_preset['name'], 'activeUsers')

                recent_preset = next((p for p in presets if p['preset_name'] == 'recent_items'), None)
                self.assertIsNotNone(recent_preset)
                self.assertEqual(recent_preset['name'], 'recentItems')

    def test_custom_mutation_naming(self):
        """Test that custom mutations have camelCase names."""
        with unittest.mock.patch('rail_django.extensions.metadata.extractor.get_model_graphql_meta') as mock_get_meta:
            mock_get_meta.return_value = MagicMock(custom_metadata=None, field_groups=[])

            with unittest.mock.patch('rail_django.extensions.metadata.extractor.apps.get_model') as mock_get_model:
                mock_get_model.return_value = FieldNameTestModel

                # Mock MutationGeneratorSettings to disable CRUD to focus on custom
                with unittest.mock.patch('rail_django.extensions.metadata.extractor.MutationGeneratorSettings') as mock_settings_cls:
                    mock_settings = MagicMock()
                    mock_settings.enable_create = False
                    mock_settings.enable_update = False
                    mock_settings.enable_delete = False
                    mock_settings_cls.from_schema.return_value = mock_settings

                    # Mock ModelIntrospector
                    with unittest.mock.patch('rail_django.extensions.metadata.extractor.ModelIntrospector') as mock_introspector_cls:
                        mock_introspector = MagicMock()
                        mock_method_info = MagicMock()
                        mock_method_info.is_mutation = True
                        mock_method_info.method.__doc__ = "Test doc"

                        mock_introspector.get_model_methods.return_value = {
                            "custom_action": mock_method_info,
                            "do_something": mock_method_info
                        }
                        mock_introspector_cls.for_model.return_value = mock_introspector

                        # Mock other extractors
                        self.extractor._extract_fields = MagicMock(return_value=[])
                        self.extractor._extract_relationships = MagicMock(return_value=[])
                        self.extractor._extract_filters = MagicMock(return_value=[])
                        self.extractor._extract_filter_config = MagicMock(return_value={})
                        self.extractor._extract_relation_filters = MagicMock(return_value=[])
                        self.extractor._extract_permissions = MagicMock(return_value={})
                        self.extractor._extract_field_groups = MagicMock(return_value=[])
                        self.extractor._extract_templates = MagicMock(return_value=[])

                        # We are testing _extract_mutations logic which is in the class
                        result = self.extractor.extract('test_metadata_field_names', 'FieldNameTestModel', self.user)

                        mutations = result['mutations']

                        custom_action = next((m for m in mutations if m['method_name'] == 'custom_action'), None)
                        self.assertIsNotNone(custom_action)
                        self.assertEqual(custom_action['name'], 'customAction')

                        do_something = next((m for m in mutations if m['method_name'] == 'do_something'), None)
                        self.assertIsNotNone(do_something)
                        self.assertEqual(do_something['name'], 'doSomething')


