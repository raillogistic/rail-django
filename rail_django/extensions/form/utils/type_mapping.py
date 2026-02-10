"""
Type mapping helpers for the Form API.
"""

from __future__ import annotations

from typing import Any

from django.db import models


FIELD_INPUT_TYPE_MAP: dict[type[models.Field], str] = {
    models.EmailField: "EMAIL",
    models.URLField: "URL",
    models.SlugField: "SLUG",
    models.UUIDField: "UUID",
    models.AutoField: "NUMBER",
    models.BigAutoField: "NUMBER",
    models.SmallAutoField: "NUMBER",
    models.IntegerField: "NUMBER",
    models.SmallIntegerField: "NUMBER",
    models.BigIntegerField: "NUMBER",
    models.PositiveIntegerField: "NUMBER",
    models.PositiveSmallIntegerField: "NUMBER",
    models.PositiveBigIntegerField: "NUMBER",
    models.FloatField: "DECIMAL",
    models.DecimalField: "DECIMAL",
    models.BooleanField: "SWITCH",
    models.DateField: "DATE",
    models.TimeField: "TIME",
    models.DateTimeField: "DATETIME",
    models.DurationField: "TEXT",
    models.JSONField: "JSON",
    models.TextField: "TEXTAREA",
    models.GenericIPAddressField: "TEXT",
    models.CharField: "TEXT",
    models.FileField: "FILE",
    models.ImageField: "IMAGE",
}


def map_field_input_type(field: models.Field) -> str:
    """Map a Django field to a Form API input type."""
    output_field = getattr(field, "output_field", None)
    if output_field is not None and type(field).__name__ == "GeneratedField":
        return map_field_input_type(output_field)

    if hasattr(field, "choices") and field.choices:
        # Choices are represented as selects unless explicitly overridden.
        return "SELECT"

    for field_type, input_type in FIELD_INPUT_TYPE_MAP.items():
        if isinstance(field, field_type):
            return input_type

    # Fallback to text for unknown types
    return "TEXT"


def map_graphql_type(field: models.Field) -> str:
    """Map Django field to GraphQL scalar name."""
    output_field = getattr(field, "output_field", None)
    if output_field is not None and type(field).__name__ == "GeneratedField":
        return map_graphql_type(output_field)

    field_type = type(field).__name__
    mapping = {
        "AutoField": "ID",
        "BigAutoField": "ID",
        "SmallAutoField": "ID",
        "CharField": "String",
        "TextField": "String",
        "SlugField": "String",
        "URLField": "String",
        "GenericIPAddressField": "String",
        "EmailField": "String",
        "UUIDField": "String",
        "IntegerField": "Int",
        "SmallIntegerField": "Int",
        "BigIntegerField": "Int",
        "PositiveIntegerField": "Int",
        "PositiveSmallIntegerField": "Int",
        "PositiveBigIntegerField": "Int",
        "FloatField": "Float",
        "DecimalField": "Float",
        "BooleanField": "Boolean",
        "NullBooleanField": "Boolean",
        "DateField": "Date",
        "DateTimeField": "DateTime",
        "TimeField": "Time",
        "DurationField": "String",
        "JSONField": "JSONString",
        "FileField": "String",
        "FilePathField": "String",
        "ImageField": "String",
        "BinaryField": "String",
    }
    return mapping.get(field_type, "String")


def map_python_type(field: models.Field) -> str:
    """Map Django field to a Python type name string."""
    output_field = getattr(field, "output_field", None)
    if output_field is not None and type(field).__name__ == "GeneratedField":
        return map_python_type(output_field)

    field_type = type(field).__name__
    mapping = {
        "AutoField": "int",
        "BigAutoField": "int",
        "SmallAutoField": "int",
        "CharField": "str",
        "TextField": "str",
        "SlugField": "str",
        "URLField": "str",
        "GenericIPAddressField": "str",
        "EmailField": "str",
        "UUIDField": "str",
        "IntegerField": "int",
        "SmallIntegerField": "int",
        "BigIntegerField": "int",
        "PositiveIntegerField": "int",
        "PositiveSmallIntegerField": "int",
        "PositiveBigIntegerField": "int",
        "FloatField": "float",
        "DecimalField": "Decimal",
        "BooleanField": "bool",
        "NullBooleanField": "bool",
        "DateField": "date",
        "DateTimeField": "datetime",
        "TimeField": "time",
        "DurationField": "timedelta",
        "JSONField": "dict",
        "FileField": "str",
        "FilePathField": "str",
        "ImageField": "str",
        "BinaryField": "bytes",
    }
    return mapping.get(field_type, "str")


def map_default_value(value: Any) -> Any:
    """Normalize default values to JSON-serializable data."""
    if callable(value):
        return None
    return value
