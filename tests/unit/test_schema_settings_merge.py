import pytest
from django.test import TestCase, override_settings

from rail_django.core.registry import schema_registry
from rail_django.core.settings.schema_settings import SchemaSettings


pytestmark = pytest.mark.unit


class TestSchemaSettingsMerge(TestCase):
    @override_settings(
        RAIL_DJANGO_GRAPHQL={
            "schema_settings": {
                "mutation_extensions": ["apps.users.mutations.UsersMutations"],
                "query_extensions": ["rail_django.extensions.metadata_v2.ModelSchemaQueryV2"],
                "authentication_required": True,
            },
        },
        RAIL_DJANGO_GRAPHQL_SCHEMAS={
            "gql": {
                "schema_settings": {
                    "authentication_required": False,
                },
            },
        },
    )
    def test_global_schema_settings_are_inherited_by_named_schema(self):
        schema_registry.clear()
        schema_registry.discover_schemas()

        gql_settings = SchemaSettings.from_schema("gql")

        assert gql_settings.authentication_required is False
        assert "apps.users.mutations.UsersMutations" in gql_settings.mutation_extensions
        assert (
            "rail_django.extensions.metadata_v2.ModelSchemaQueryV2"
            in gql_settings.query_extensions
        )
