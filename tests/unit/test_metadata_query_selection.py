from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.db import models
from django.test import TestCase, override_settings
from graphql import parse

from rail_django.extensions.metadata.extractor import ModelSchemaExtractor
from rail_django.extensions.metadata.queries import (
    ModelSchemaQuery,
    _collect_requested_subfields,
    _collect_requested_section_subfields,
)


class QuerySelectionTestModel(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "test_metadata_query_selection"


class TestMetadataQuerySelection(TestCase):
    @override_settings(DEBUG=True)
    @patch("rail_django.extensions.metadata.extractor.get_model_version")
    @patch("rail_django.extensions.metadata.extractor.get_model_graphql_meta")
    @patch("rail_django.extensions.metadata.extractor.apps.get_model")
    def test_extractor_only_computes_requested_sections(
        self,
        mock_get_model,
        mock_get_meta,
        mock_get_version,
    ):
        mock_get_model.return_value = QuerySelectionTestModel
        mock_get_meta.return_value = MagicMock()
        mock_get_version.return_value = "v1"

        extractor = ModelSchemaExtractor()
        extractor._extract_fields = MagicMock(return_value=[])
        extractor._extract_filter_config = MagicMock(return_value={})
        extractor._extract_mutations = MagicMock(return_value=[])
        extractor._extract_templates = MagicMock(return_value=[])

        result = extractor.extract(
            "test_metadata_query_selection",
            "QuerySelectionTestModel",
            user=MagicMock(),
            include_sections={"fields", "filter_config"},
        )

        extractor._extract_fields.assert_called_once()
        extractor._extract_filter_config.assert_called_once()
        extractor._extract_mutations.assert_not_called()
        extractor._extract_templates.assert_not_called()

        self.assertEqual(result["metadata_version"], "v1")
        self.assertIn("fields", result)
        self.assertIn("filter_config", result)
        self.assertNotIn("mutations", result)
        self.assertNotIn("templates", result)

    def test_collect_requested_subfields_handles_nested_and_fragment(self):
        document = parse(
            """
            query TestQuery {
              modelSchema(app: "inventory", model: "Product") {
                fields { name }
                ...ConfigFields
              }
            }

            fragment ConfigFields on ModelSchemaType {
              filterConfig { supportsQuick }
              metadataVersion
            }
            """
        )
        operation = document.definitions[0]
        model_schema_field = operation.selection_set.selections[0]
        fragments = {
            definition.name.value: definition
            for definition in document.definitions[1:]
        }
        info = SimpleNamespace(field_nodes=[model_schema_field], fragments=fragments)

        requested = _collect_requested_subfields(info)
        self.assertIn("fields", requested)
        self.assertIn("filter_config", requested)
        self.assertIn("metadata_version", requested)

        section_subfields = _collect_requested_section_subfields(info)
        self.assertIn("fields", section_subfields)
        self.assertIn("name", section_subfields["fields"])
        self.assertIn("filter_config", section_subfields)
        self.assertIn("supports_quick", section_subfields["filter_config"])

    @patch("rail_django.extensions.metadata.queries._collect_requested_subfields")
    @patch("rail_django.extensions.metadata.queries._collect_requested_section_subfields")
    @patch("rail_django.extensions.metadata.queries.ModelSchemaExtractor")
    @patch("rail_django.extensions.metadata.queries._user_can_discover_model")
    @patch("rail_django.extensions.metadata.queries.apps.get_model")
    def test_query_forwards_requested_sections_to_extractor(
        self,
        mock_get_model,
        mock_can_discover,
        mock_extractor_cls,
        mock_collect_section_subfields,
        mock_collect_sections,
    ):
        mock_model = MagicMock()
        mock_get_model.return_value = mock_model
        mock_can_discover.return_value = True
        mock_collect_sections.return_value = {"fields", "filter_config"}
        mock_collect_section_subfields.return_value = {
            "fields": {"name", "field_name"}
        }

        extractor_instance = mock_extractor_cls.return_value
        extractor_instance.extract.return_value = {"app": "inventory", "model": "Product"}

        info = SimpleNamespace(
            context=SimpleNamespace(user=MagicMock(), schema_name="default"),
            field_nodes=[],
            fragments={},
        )

        result = ModelSchemaQuery().resolve_modelSchema(
            info, app="inventory", model="Product"
        )

        self.assertEqual(result["model"], "Product")
        extractor_instance.extract.assert_called_once_with(
            "inventory",
            "Product",
            user=info.context.user,
            object_id=None,
            include_sections={"fields", "filter_config"},
            include_section_subfields={"fields": {"name", "field_name"}},
        )
