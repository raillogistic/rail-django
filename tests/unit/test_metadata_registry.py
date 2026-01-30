
from django.db import models
from django.test import TestCase
from rail_django.extensions.metadata.mapping import registry, FieldTypeRegistry

class CustomField(models.Field):
    pass

class TestFieldTypeRegistry(TestCase):
    def setUp(self):
        # Reset registry instance for each test to avoid side effects
        FieldTypeRegistry._instance = None
        self.registry = FieldTypeRegistry.get_instance()

    def test_default_mappings(self):
        """Test that default mappings are initialized correctly."""
        char_field = models.CharField()
        int_field = models.IntegerField()

        self.assertEqual(self.registry.get_graphql_type(char_field), "String")
        self.assertEqual(self.registry.get_graphql_type(int_field), "Int")

        self.assertEqual(self.registry.get_python_type(char_field), "str")
        self.assertEqual(self.registry.get_python_type(int_field), "int")

    def test_custom_mapping(self):
        """Test registering and using a custom field mapping."""
        # Register custom field
        self.registry.register_graphql_mapping(CustomField, "CustomType")
        self.registry.register_python_mapping(CustomField, "custom_obj")

        field = CustomField()
        self.assertEqual(self.registry.get_graphql_type(field), "CustomType")
        self.assertEqual(self.registry.get_python_type(field), "custom_obj")

    def test_overwrite_mapping(self):
        """Test overwriting an existing mapping."""
        char_field = models.CharField()

        # Default
        self.assertEqual(self.registry.get_graphql_type(char_field), "String")

        # Overwrite
        self.registry.register_graphql_mapping("CharField", "OverwrittenString")

        self.assertEqual(self.registry.get_graphql_type(char_field), "OverwrittenString")

        # Restore default (good practice for shared state, though setUp handles it)
        self.registry.register_graphql_mapping("CharField", "String")

    def test_unknown_field_defaults(self):
        """Test behavior for unknown fields."""
        class UnknownField(models.Field):
            pass

        field = UnknownField()
        # Should return defaults
        self.assertEqual(self.registry.get_graphql_type(field), "String")
        self.assertEqual(self.registry.get_python_type(field), "str")
