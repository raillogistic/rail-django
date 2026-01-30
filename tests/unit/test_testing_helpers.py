import pytest
from django.test import TestCase
from rail_django.testing import override_rail_settings, override_rail_schema_settings
from rail_django.config_proxy import get_setting, _RUNTIME_SCHEMA_SETTINGS

@pytest.mark.unit
class TestTestingHelpers(TestCase):
    def test_override_rail_schema_settings(self):
        """Test that schema-specific runtime overrides work and isolate."""
        schema_name = "test_schema"
        key = "performance_settings.max_query_depth"

        # Initial state (from defaults or settings)
        initial_val = get_setting(key, schema_name=schema_name)

        with override_rail_schema_settings(schema_name, performance_settings={"max_query_depth": 999}):
            assert get_setting(key, schema_name=schema_name) == 999
            # Verify it doesn't leak to other schemas
            assert get_setting(key, schema_name="other") != 999

        # Verify restoration
        assert get_setting(key, schema_name=schema_name) == initial_val

    def test_override_rail_settings_global_isolation(self):
        """Test that global override clears runtime settings to ensure precedence."""
        schema_name = "test_schema"
        key = "performance_settings.max_query_depth"

        # Set a runtime setting that would normally take precedence
        _RUNTIME_SCHEMA_SETTINGS[schema_name] = {"performance_settings": {"max_query_depth": 500}}

        try:
            # override_rail_settings uses Django settings.
            # It should clear _RUNTIME_SCHEMA_SETTINGS during yield.
            with override_rail_settings(schema_settings={schema_name: {"performance_settings": {"max_query_depth": 100}}}):
                assert get_setting(key, schema_name=schema_name) == 100

            # Verify restoration of runtime settings
            assert _RUNTIME_SCHEMA_SETTINGS[schema_name]["performance_settings"]["max_query_depth"] == 500
        finally:
            _RUNTIME_SCHEMA_SETTINGS.pop(schema_name, None)

    def test_nested_overrides(self):
        """Test that overrides can be nested correctly."""
        schema = "nested_test"
        key = "security_settings.enable_introspection"

        with override_rail_schema_settings(schema, security_settings={"enable_introspection": True}):
            assert get_setting(key, schema_name=schema) is True

            with override_rail_schema_settings(schema, security_settings={"enable_introspection": False}):
                assert get_setting(key, schema_name=schema) is False

            assert get_setting(key, schema_name=schema) is True
