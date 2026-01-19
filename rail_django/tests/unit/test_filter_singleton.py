"""
Unit tests for filter singleton pattern and bounded cache (Phase 4).

Tests the singleton registry functions and cache eviction behavior
for NestedFilterInputGenerator and NestedFilterApplicator.
"""

import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.unit


class TestFilterSingletonRegistry:
    """Test singleton registry functions for filter generators and applicators."""

    def test_get_nested_filter_generator_returns_same_instance(self):
        """get_nested_filter_generator should return the same instance for same schema."""
        from rail_django.generators.filter_inputs import (
            get_nested_filter_generator,
            clear_filter_caches,
        )

        # Clear any existing caches first
        clear_filter_caches()

        # Get generator twice for same schema
        gen1 = get_nested_filter_generator("test_schema")
        gen2 = get_nested_filter_generator("test_schema")

        assert gen1 is gen2, "Should return same instance for same schema"

        # Cleanup
        clear_filter_caches()

    def test_get_nested_filter_generator_different_schemas(self):
        """get_nested_filter_generator should return different instances for different schemas."""
        from rail_django.generators.filter_inputs import (
            get_nested_filter_generator,
            clear_filter_caches,
        )

        clear_filter_caches()

        gen1 = get_nested_filter_generator("schema_a")
        gen2 = get_nested_filter_generator("schema_b")

        assert gen1 is not gen2, "Should return different instances for different schemas"
        assert gen1.schema_name == "schema_a"
        assert gen2.schema_name == "schema_b"

        clear_filter_caches()

    def test_get_nested_filter_applicator_returns_same_instance(self):
        """get_nested_filter_applicator should return the same instance for same schema."""
        from rail_django.generators.filter_inputs import (
            get_nested_filter_applicator,
            clear_filter_caches,
        )

        clear_filter_caches()

        app1 = get_nested_filter_applicator("test_schema")
        app2 = get_nested_filter_applicator("test_schema")

        assert app1 is app2, "Should return same instance for same schema"

        clear_filter_caches()

    def test_get_nested_filter_applicator_different_schemas(self):
        """get_nested_filter_applicator should return different instances for different schemas."""
        from rail_django.generators.filter_inputs import (
            get_nested_filter_applicator,
            clear_filter_caches,
        )

        clear_filter_caches()

        app1 = get_nested_filter_applicator("schema_x")
        app2 = get_nested_filter_applicator("schema_y")

        assert app1 is not app2, "Should return different instances for different schemas"
        assert app1.schema_name == "schema_x"
        assert app2.schema_name == "schema_y"

        clear_filter_caches()

    def test_clear_filter_caches_all(self):
        """clear_filter_caches() should clear all cached instances."""
        from rail_django.generators.filter_inputs import (
            get_nested_filter_generator,
            get_nested_filter_applicator,
            clear_filter_caches,
            _filter_generator_registry,
            _filter_applicator_registry,
        )

        clear_filter_caches()

        # Create some instances
        get_nested_filter_generator("schema1")
        get_nested_filter_generator("schema2")
        get_nested_filter_applicator("schema1")
        get_nested_filter_applicator("schema2")

        assert len(_filter_generator_registry) == 2
        assert len(_filter_applicator_registry) == 2

        # Clear all
        clear_filter_caches()

        assert len(_filter_generator_registry) == 0
        assert len(_filter_applicator_registry) == 0

    def test_clear_filter_caches_specific_schema(self):
        """clear_filter_caches(schema_name) should clear only that schema."""
        from rail_django.generators.filter_inputs import (
            get_nested_filter_generator,
            get_nested_filter_applicator,
            clear_filter_caches,
            _filter_generator_registry,
            _filter_applicator_registry,
        )

        clear_filter_caches()

        # Create instances for multiple schemas
        get_nested_filter_generator("keep_schema")
        get_nested_filter_generator("remove_schema")
        get_nested_filter_applicator("keep_schema")
        get_nested_filter_applicator("remove_schema")

        # Clear only one schema
        clear_filter_caches("remove_schema")

        assert "keep_schema" in _filter_generator_registry
        assert "remove_schema" not in _filter_generator_registry
        assert "keep_schema" in _filter_applicator_registry
        assert "remove_schema" not in _filter_applicator_registry

        clear_filter_caches()

    def test_default_schema_name(self):
        """Default schema name should be 'default'."""
        from rail_django.generators.filter_inputs import (
            get_nested_filter_generator,
            get_nested_filter_applicator,
            clear_filter_caches,
        )

        clear_filter_caches()

        gen = get_nested_filter_generator()
        app = get_nested_filter_applicator()

        assert gen.schema_name == "default"
        assert app.schema_name == "default"

        clear_filter_caches()


class TestFilterGeneratorBoundedCache:
    """Test bounded cache behavior for NestedFilterInputGenerator."""

    def test_instance_level_cache(self):
        """Filter input cache should be instance-level, not class-level."""
        from rail_django.generators.filter_inputs import NestedFilterInputGenerator

        gen1 = NestedFilterInputGenerator(schema_name="instance_test_1")
        gen2 = NestedFilterInputGenerator(schema_name="instance_test_2")

        # Each instance should have its own cache
        assert gen1._filter_input_cache is not gen2._filter_input_cache
        assert gen1._generation_stack is not gen2._generation_stack

    def test_clear_cache_method(self):
        """Generator should have a clear_cache method."""
        from rail_django.generators.filter_inputs import NestedFilterInputGenerator

        gen = NestedFilterInputGenerator(schema_name="cache_test")

        # Add something to internal state
        gen._filter_input_cache["test_key"] = "test_value"
        gen._generation_stack.add("test_entry")

        # Clear should reset both
        gen.clear_cache()

        assert len(gen._filter_input_cache) == 0
        assert len(gen._generation_stack) == 0

    def test_cache_max_size_parameter(self):
        """Generator should accept cache_max_size parameter."""
        from rail_django.generators.filter_inputs import NestedFilterInputGenerator

        gen = NestedFilterInputGenerator(schema_name="size_test", cache_max_size=50)

        assert gen.cache_max_size == 50

    def test_evict_cache_if_needed(self):
        """Cache eviction should remove oldest entries when full."""
        from rail_django.generators.filter_inputs import NestedFilterInputGenerator

        # Create generator with small cache size for testing
        gen = NestedFilterInputGenerator(schema_name="evict_test", cache_max_size=10)

        # Fill the cache
        for i in range(10):
            gen._filter_input_cache[f"key_{i}"] = f"value_{i}"

        assert len(gen._filter_input_cache) == 10

        # Trigger eviction
        gen._evict_cache_if_needed()

        # Should have evicted 10% (1 entry)
        assert len(gen._filter_input_cache) == 9
        # First entry should be gone (oldest)
        assert "key_0" not in gen._filter_input_cache
        # Later entries should remain
        assert "key_9" in gen._filter_input_cache

    def test_eviction_minimum_one_entry(self):
        """Eviction should remove at least one entry even with small cache."""
        from rail_django.generators.filter_inputs import NestedFilterInputGenerator

        # Create generator with very small cache
        gen = NestedFilterInputGenerator(schema_name="min_evict", cache_max_size=3)

        # Fill the cache
        gen._filter_input_cache["a"] = 1
        gen._filter_input_cache["b"] = 2
        gen._filter_input_cache["c"] = 3

        gen._evict_cache_if_needed()

        # 10% of 3 = 0, but should evict at least 1
        assert len(gen._filter_input_cache) == 2
        assert "a" not in gen._filter_input_cache


class TestQueryGeneratorUseSingleton:
    """Test that query generators use singleton pattern for filters."""

    def test_queries_list_uses_singleton(self):
        """queries_list._get_nested_filter_generator should use singleton."""
        from rail_django.generators.queries_list import (
            _get_nested_filter_generator,
            _get_nested_filter_applicator,
        )
        from rail_django.generators.filter_inputs import clear_filter_caches

        clear_filter_caches()

        gen1 = _get_nested_filter_generator("singleton_test")
        gen2 = _get_nested_filter_generator("singleton_test")

        assert gen1 is gen2

        app1 = _get_nested_filter_applicator("singleton_test")
        app2 = _get_nested_filter_applicator("singleton_test")

        assert app1 is app2

        clear_filter_caches()

    def test_queries_pagination_uses_singleton(self):
        """queries_pagination._get_nested_filter_generator should use singleton."""
        from rail_django.generators.queries_pagination import (
            _get_nested_filter_generator,
            _get_nested_filter_applicator,
        )
        from rail_django.generators.filter_inputs import clear_filter_caches

        clear_filter_caches()

        gen1 = _get_nested_filter_generator("pagination_test")
        gen2 = _get_nested_filter_generator("pagination_test")

        assert gen1 is gen2

        app1 = _get_nested_filter_applicator("pagination_test")
        app2 = _get_nested_filter_applicator("pagination_test")

        assert app1 is app2

        clear_filter_caches()

    def test_queries_grouping_uses_singleton(self):
        """queries_grouping._get_nested_filter_generator should use singleton."""
        from rail_django.generators.queries_grouping import (
            _get_nested_filter_generator,
            _get_nested_filter_applicator,
        )
        from rail_django.generators.filter_inputs import clear_filter_caches

        clear_filter_caches()

        gen1 = _get_nested_filter_generator("grouping_test")
        gen2 = _get_nested_filter_generator("grouping_test")

        assert gen1 is gen2

        app1 = _get_nested_filter_applicator("grouping_test")
        app2 = _get_nested_filter_applicator("grouping_test")

        assert app1 is app2

        clear_filter_caches()
