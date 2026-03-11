from collections import OrderedDict
from unittest.mock import Mock, patch

import pytest

from rail_django.core.registry import SchemaInfo, SchemaRegistry
from rail_django.core.registry.builders import get_schema_instance
from rail_django.core.schema import AutoSchemaGenerator
from rail_django.generators.mutations import MutationGenerator
from rail_django.generators.queries import QueryGenerator
from rail_django.generators.types import TypeGenerator
from test_app.models import Category, Post


@pytest.mark.unit
def test_clear_builders_disconnects_cached_builders():
    registry = SchemaRegistry()
    builder = Mock()
    registry._schema_builders["default"] = builder

    registry.clear_builders()

    builder.disconnect_signals.assert_called_once()
    assert registry._schema_builders == {}


@pytest.mark.unit
def test_unregister_schema_disconnects_cached_builder():
    registry = SchemaRegistry()
    builder = Mock()
    registry._schemas["default"] = SchemaInfo(name="default")
    registry._schema_builders["default"] = builder

    assert registry.unregister_schema("default") is True

    builder.disconnect_signals.assert_called_once()
    assert "default" not in registry._schema_builders


@pytest.mark.unit
def test_get_schema_instance_records_post_build_version():
    registry = SchemaRegistry()
    registry.register_schema("default")

    builder = Mock()
    builder._schema = None
    builder.get_schema.return_value = "schema"
    builder.get_schema_version.side_effect = [0, 1, 1]

    with patch(
        "rail_django.core.registry.builders.get_schema_builder",
        return_value=builder,
    ):
        assert get_schema_instance(registry, "default") == "schema"
        assert registry._schema_instance_cache["default"]["version"] == 1

        builder._schema = object()
        assert get_schema_instance(registry, "default") == "schema"

    assert builder.get_schema.call_count == 1


@pytest.mark.unit
def test_type_generator_caches_field_visibility_checks():
    generator = TypeGenerator()

    with patch.object(
        generator, "_get_excluded_fields", wraps=generator._get_excluded_fields
    ) as excluded_mock, patch.object(
        generator, "_get_included_fields", wraps=generator._get_included_fields
    ) as included_mock:
        assert generator._should_include_field(Category, "name") is True
        assert generator._should_include_field(Category, "name") is True
        assert generator._should_include_field(
            Category, "name", for_input=True
        ) is True
        assert generator._should_include_field(
            Category, "name", for_input=True
        ) is True

    assert excluded_mock.call_count == 2
    assert included_mock.call_count == 2


@pytest.mark.unit
def test_mutation_generator_reuses_cached_mutation_fields():
    generator = MutationGenerator(TypeGenerator())

    first = generator.generate_all_mutations(Category)
    second = generator.generate_all_mutations(Category)

    assert first["createCategory"] is second["createCategory"]
    assert first["updateCategory"] is second["updateCategory"]
    assert first["deleteCategory"] is second["deleteCategory"]


@pytest.mark.unit
def test_query_generator_reuses_cached_query_fields():
    generator = QueryGenerator(TypeGenerator())

    assert generator.generate_list_query(Category) is generator.generate_list_query(
        Category
    )
    assert generator.generate_paginated_query(
        Category
    ) is generator.generate_paginated_query(Category)
    assert generator.generate_grouping_query(
        Category
    ) is generator.generate_grouping_query(Category)


@pytest.mark.unit
def test_auto_schema_generator_evicts_oldest_builder():
    generator = AutoSchemaGenerator(max_cached_builders=1)
    first_builder = Mock()
    second_builder = Mock()

    generator._builders = OrderedDict(
        [
            (("category",), first_builder),
            (("post",), second_builder),
        ]
    )
    generator._schema_cache = OrderedDict(
        [
            (("category",), "schema-1"),
            (("post",), "schema-2"),
        ]
    )

    generator._evict_oldest_builder_if_needed()

    first_builder.disconnect_signals.assert_called_once()
    assert ("category",) not in generator._builders
    assert ("category",) not in generator._schema_cache


@pytest.mark.unit
def test_auto_schema_generator_restores_builder_overrides():
    generator = AutoSchemaGenerator()
    query_extension = type("QueryExtension", (), {})
    generator._query_extensions.append(query_extension)

    original_discover = Mock(return_value=[])
    original_load_extensions = Mock(return_value=[])
    builder = Mock()
    builder._discover_models = original_discover
    builder._load_query_extensions = original_load_extensions
    builder._is_valid_model.side_effect = lambda model: True
    builder.get_schema.return_value = "schema"

    with patch.object(generator, "_get_builder", return_value=builder):
        assert generator.get_schema([Category, Post]) == "schema"

    assert builder._discover_models is original_discover
    assert builder._load_query_extensions is original_load_extensions
