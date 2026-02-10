
from django.db import models
from django.test import TestCase
from rail_django.extensions.metadata.mapping import registry, FieldTypeRegistry
from tests.models import TestGeneratedModel

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

    def test_extended_builtin_mappings(self):
        """Common Django field variants should have explicit mappings."""
        self.assertEqual(
            self.registry.get_graphql_type(models.PositiveBigIntegerField()), "Int"
        )
        self.assertEqual(
            self.registry.get_graphql_type(models.GenericIPAddressField()), "String"
        )
        self.assertEqual(self.registry.get_graphql_type(models.BigAutoField()), "ID")
        self.assertEqual(
            self.registry.get_python_type(models.PositiveBigIntegerField()), "int"
        )
        self.assertEqual(
            self.registry.get_python_type(models.GenericIPAddressField()), "str"
        )
        self.assertEqual(self.registry.get_python_type(models.BigAutoField()), "int")

    def test_generated_field_uses_output_field_mapping(self):
        """GeneratedField should reuse the mapping of its output_field."""
        generated = TestGeneratedModel._meta.get_field("area")
        self.assertEqual(self.registry.get_graphql_type(generated), "Int")
        self.assertEqual(self.registry.get_python_type(generated), "int")
