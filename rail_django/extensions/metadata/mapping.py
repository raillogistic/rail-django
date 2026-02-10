from typing import Dict, Type, Union
from django.db import models

class FieldTypeRegistry:
    """
    Registry for mapping Django field types to GraphQL and Python types.
    Allows for extensibility by registering custom field types.
    """
    _instance = None

    def __init__(self):
        self._graphql_mapping: Dict[str, str] = {}
        self._python_mapping: Dict[str, str] = {}
        self._initialize_defaults()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _initialize_defaults(self):
        """Initialize default Django field mappings."""
        # GraphQL Mappings
        self.register_graphql_mapping("AutoField", "ID")
        self.register_graphql_mapping("BigAutoField", "ID")
        self.register_graphql_mapping("SmallAutoField", "ID")
        self.register_graphql_mapping("CharField", "String")
        self.register_graphql_mapping("TextField", "String")
        self.register_graphql_mapping("SlugField", "String")
        self.register_graphql_mapping("URLField", "String")
        self.register_graphql_mapping("GenericIPAddressField", "String")
        self.register_graphql_mapping("EmailField", "String")
        self.register_graphql_mapping("UUIDField", "String")
        self.register_graphql_mapping("IntegerField", "Int")
        self.register_graphql_mapping("SmallIntegerField", "Int")
        self.register_graphql_mapping("BigIntegerField", "Int")
        self.register_graphql_mapping("PositiveIntegerField", "Int")
        self.register_graphql_mapping("PositiveSmallIntegerField", "Int")
        self.register_graphql_mapping("PositiveBigIntegerField", "Int")
        self.register_graphql_mapping("FloatField", "Float")
        self.register_graphql_mapping("DecimalField", "Float")
        self.register_graphql_mapping("BooleanField", "Boolean")
        self.register_graphql_mapping("NullBooleanField", "Boolean")
        self.register_graphql_mapping("DateField", "Date")
        self.register_graphql_mapping("DateTimeField", "DateTime")
        self.register_graphql_mapping("TimeField", "Time")
        self.register_graphql_mapping("DurationField", "String")
        self.register_graphql_mapping("JSONField", "JSONString")
        self.register_graphql_mapping("FileField", "String")
        self.register_graphql_mapping("FilePathField", "String")
        self.register_graphql_mapping("ImageField", "String")
        self.register_graphql_mapping("BinaryField", "String")
        self.register_graphql_mapping("ForeignKey", "ID")
        self.register_graphql_mapping("OneToOneField", "ID")

        # Python Mappings
        self.register_python_mapping("AutoField", "int")
        self.register_python_mapping("BigAutoField", "int")
        self.register_python_mapping("SmallAutoField", "int")
        self.register_python_mapping("CharField", "str")
        self.register_python_mapping("TextField", "str")
        self.register_python_mapping("SlugField", "str")
        self.register_python_mapping("URLField", "str")
        self.register_python_mapping("GenericIPAddressField", "str")
        self.register_python_mapping("EmailField", "str")
        self.register_python_mapping("UUIDField", "str")
        self.register_python_mapping("IntegerField", "int")
        self.register_python_mapping("SmallIntegerField", "int")
        self.register_python_mapping("BigIntegerField", "int")
        self.register_python_mapping("PositiveIntegerField", "int")
        self.register_python_mapping("PositiveSmallIntegerField", "int")
        self.register_python_mapping("PositiveBigIntegerField", "int")
        self.register_python_mapping("FloatField", "float")
        self.register_python_mapping("DecimalField", "Decimal")
        self.register_python_mapping("BooleanField", "bool")
        self.register_python_mapping("DateField", "date")
        self.register_python_mapping("DateTimeField", "datetime")
        self.register_python_mapping("TimeField", "time")
        self.register_python_mapping("DurationField", "timedelta")
        self.register_python_mapping("JSONField", "dict")
        self.register_python_mapping("FileField", "str")
        self.register_python_mapping("FilePathField", "str")
        self.register_python_mapping("ImageField", "str")
        self.register_python_mapping("BinaryField", "bytes")

    def register_graphql_mapping(self, field_type: Union[str, Type[models.Field]], graphql_type: str):
        """
        Register a mapping from a Django field type to a GraphQL type.

        Args:
            field_type: The Django field class name (str) or class itself.
            graphql_type: The GraphQL scalar type name.
        """
        key = field_type if isinstance(field_type, str) else field_type.__name__
        self._graphql_mapping[key] = graphql_type

    def register_python_mapping(self, field_type: Union[str, Type[models.Field]], python_type: str):
        """
        Register a mapping from a Django field type to a Python type name.

        Args:
            field_type: The Django field class name (str) or class itself.
            python_type: The Python type name.
        """
        key = field_type if isinstance(field_type, str) else field_type.__name__
        self._python_mapping[key] = python_type

    def get_graphql_type(self, field: models.Field) -> str:
        """Get GraphQL type for a field instance."""
        # Django 5 GeneratedField exposes type via output_field.
        output_field = getattr(field, "output_field", None)
        if output_field is not None and type(field).__name__ == "GeneratedField":
            return self.get_graphql_type(output_field)
        field_type = type(field).__name__
        return self._graphql_mapping.get(field_type, "String")

    def get_python_type(self, field: models.Field) -> str:
        """Get Python type name for a field instance."""
        output_field = getattr(field, "output_field", None)
        if output_field is not None and type(field).__name__ == "GeneratedField":
            return self.get_python_type(output_field)
        field_type = type(field).__name__
        return self._python_mapping.get(field_type, "str")

# Global accessor
registry = FieldTypeRegistry.get_instance()
