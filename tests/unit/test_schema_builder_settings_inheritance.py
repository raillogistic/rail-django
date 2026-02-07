import pytest
from django.test import TestCase, override_settings

from rail_django.core.registry import schema_registry


pytestmark = pytest.mark.unit


class TestSchemaBuilderSettingsInheritance(TestCase):
    @override_settings(
        RAIL_DJANGO_GRAPHQL={
            "schema_settings": {
                "mutation_extensions": ["apps.users.mutations.UsersMutations"],
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
    def test_builder_inherits_global_schema_settings(self):
        schema_registry.clear()
        schema_registry.discover_schemas()

        builder = schema_registry.get_schema_builder("gql")

        assert builder.settings.authentication_required is False
        assert "apps.users.mutations.UsersMutations" in builder.settings.mutation_extensions
