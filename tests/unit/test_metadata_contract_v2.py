from django.test import TestCase

from rail_django.extensions.metadata.types import (
    FilterSchemaType,
    ModelSchemaType,
    RelationFilterSchemaType,
)


class TestMetadataContractV2(TestCase):
    """
    Contract test skeleton for the canonical metadata v2 GraphQL schema.

    These tests intentionally focus on top-level field presence and naming.
    Additional value/shape assertions can be added incrementally.
    """

    def test_model_schema_core_fields_exist(self):
        fields = ModelSchemaType._meta.fields
        for key in (
            "app",
            "model",
            "fields",
            "relationships",
            "filters",
            "filter_config",
            "relation_filters",
            "mutations",
            "permissions",
            "metadata_version",
        ):
            self.assertIn(key, fields)

    def test_filter_schema_uses_canonical_name_pair(self):
        fields = FilterSchemaType._meta.fields
        self.assertIn("name", fields)
        self.assertIn("field_name", fields)

    def test_relation_filter_schema_uses_canonical_name_pair(self):
        fields = RelationFilterSchemaType._meta.fields
        self.assertIn("name", fields)
        self.assertIn("field_name", fields)

