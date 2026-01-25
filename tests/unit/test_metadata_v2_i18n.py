
from django.db import models
from django.test import TestCase, override_settings
from django.utils.translation import activate, deactivate
from django.utils.translation import gettext_lazy as _
from rail_django.extensions.metadata_v2.filter_extractor import FilterExtractorMixin
from rail_django.extensions.metadata_v2.permissions_extractor import PermissionExtractorMixin
from unittest.mock import MagicMock, patch

class I18nTestModel(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = 'test_metadata_v2_i18n'
        verbose_name = "Test Item"

class TestI18nSupport(TestCase):
    def setUp(self):
        self.filter_extractor = FilterExtractorMixin()
        self.filter_extractor.schema_name = "default"
        self.perm_extractor = PermissionExtractorMixin()

    def tearDown(self):
        deactivate()

    def test_permission_extractor_lazy_translation(self):
        """Verify that PermissionExtractor uses translation."""
        # Use a mock translation to verify it's being called/used
        with patch('rail_django.extensions.metadata_v2.permissions_extractor._') as mock_gettext:
            mock_gettext.side_effect = lambda x: f"Translated[{x}]"

            mutations_mock = self.perm_extractor._extract_mutations(I18nTestModel, user=None)
            create_mutation_mock = next(m for m in mutations_mock if m['operation'] == 'CREATE')

            expected = "Translated[Create] Test Item"
            self.assertEqual(create_mutation_mock['description'], expected)

    def test_filter_extractor_lazy_translation(self):
        """Verify that FilterExtractor uses translation for suffixes."""
        model = I18nTestModel
        field_name = "name_some"

        # Patch to_camel_case where it is defined, so the local import picks up the mock
        with patch('graphene.utils.str_converters.to_camel_case') as mock_to_camel:
            mock_to_camel.side_effect = lambda x: x

            # Mock the input field and its type hierarchy
            input_field = MagicMock()
            input_type = MagicMock()
            # CRITICAL: Configure MagicMock to NOT have 'of_type' attribute to prevent infinite loop
            # in while hasattr(input_type, "of_type") loop.
            del input_type.of_type

            input_type._meta.name = "StringFilterInput"
            input_type._meta.fields = {} # empty operators for simplicity

            input_field.type = input_type

            # Patch gettext_lazy in filter_extractor to verify calls
            with patch('rail_django.extensions.metadata_v2.filter_extractor._') as mock_gettext:
                mock_gettext.side_effect = lambda x: f"TR[{x}]"

                result = self.filter_extractor._analyze_filter_field(model, field_name, input_field)

                self.assertIsNotNone(result)
                # Expected: "name (TR[At least one])"
                # "name" comes from verbose_name which is "name" (lowercase) for the field 'name'.
                # Wait, Django default verbose_name is usually "name" (lowercase) if not specified in field?
                # Actually for CharField(max_length=100), verbose_name is "name".
                # But let's check what the code does: str(getattr(model_field, "verbose_name", model_field.name))
                expected_label = "name (TR[At least one])"
                self.assertEqual(result['field_label'], expected_label)
