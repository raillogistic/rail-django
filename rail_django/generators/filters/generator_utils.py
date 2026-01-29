"""
Utility functions for the Nested Filter Input Generator.

This module provides helper functions and mappings used by the
NestedFilterInputGenerator class for determining appropriate filter
types for Django model fields, generating computed filters, array
filters, date filters, and other auxiliary filter generation tasks.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Type

import graphene
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from graphene.utils.str_converters import to_camel_case

from .types import (
    StringFilterInput,
    IntFilterInput,
    FloatFilterInput,
    BooleanFilterInput,
    IDFilterInput,
    UUIDFilterInput,
    DateFilterInput,
    DateTimeFilterInput,
    JSONFilterInput,
    ArrayFilterInput,
)

logger = logging.getLogger(__name__)

# Configuration constants
DEFAULT_MAX_NESTED_DEPTH = 3
MAX_ALLOWED_NESTED_DEPTH = 5
DEFAULT_CACHE_MAX_SIZE = 100


# Mapping from Django field types to GraphQL filter input types
FIELD_TYPE_TO_FILTER_INPUT: Dict[Type[models.Field], Type[graphene.InputObjectType]] = {
    models.CharField: StringFilterInput,
    models.TextField: StringFilterInput,
    models.EmailField: StringFilterInput,
    models.URLField: StringFilterInput,
    models.SlugField: StringFilterInput,
    models.IntegerField: IntFilterInput,
    models.SmallIntegerField: IntFilterInput,
    models.BigIntegerField: IntFilterInput,
    models.PositiveIntegerField: IntFilterInput,
    models.PositiveSmallIntegerField: IntFilterInput,
    models.PositiveBigIntegerField: IntFilterInput,
    models.AutoField: IntFilterInput,
    models.BigAutoField: IntFilterInput,
    models.FloatField: FloatFilterInput,
    models.DecimalField: FloatFilterInput,
    models.BooleanField: BooleanFilterInput,
    # models.NullBooleanField is deprecated in Django 3.1 and removed in 4.0
    # kept for compatibility with older migrations or custom fields that might still use it
    # but we treat it as BooleanFilterInput
    getattr(models, "NullBooleanField", models.BooleanField): BooleanFilterInput,
    # DateTimeField must come before DateField since DateTimeField is a subclass
    models.DateTimeField: DateTimeFilterInput,
    models.DateField: DateFilterInput,
    models.UUIDField: UUIDFilterInput,
    models.JSONField: JSONFilterInput,
}


# Mapping from filter type names to filter input classes
FILTER_TYPE_NAME_MAP: Dict[str, Type[graphene.InputObjectType]] = {
    "string": StringFilterInput,
    "int": IntFilterInput,
    "float": FloatFilterInput,
    "boolean": BooleanFilterInput,
    "date": DateFilterInput,
    "datetime": DateTimeFilterInput,
    "id": IDFilterInput,
    "uuid": UUIDFilterInput,
}


def get_filter_input_for_field(
    field: models.Field,
) -> Optional[Type[graphene.InputObjectType]]:
    """
    Get the appropriate filter input type for a Django model field.

    This function maps Django model field types to their corresponding
    GraphQL filter input types. It handles special cases like choice
    fields and file fields.

    Args:
        field: Django model field to get filter type for

    Returns:
        GraphQL InputObjectType class for filtering, or None if the
        field type is not supported for filtering
    """
    # Check for choice fields first - treat as string filters
    if hasattr(field, "choices") and field.choices:
        return StringFilterInput

    # Check for file fields - filter by file path
    if isinstance(field, (models.FileField, models.ImageField)):
        return StringFilterInput

    # Look up by field type (order matters due to inheritance)
    for field_type, filter_input in FIELD_TYPE_TO_FILTER_INPUT.items():
        if isinstance(field, field_type):
            return filter_input

    return None


def is_historical_model(model: Type[models.Model]) -> bool:
    """
    Check if model is from django-simple-history.

    Args:
        model: Django model class to check

    Returns:
        True if the model is a historical model, False otherwise
    """
    try:
        name = getattr(model, "__name__", "")
        module = getattr(model, "__module__", "")
    except (AttributeError, TypeError):
        return False

    if name.startswith("Historical"):
        return True
    return "simple_history" in module


def generate_computed_filters(
    model: Type[models.Model],
) -> Dict[str, graphene.InputField]:
    """
    Generate inputs for computed/expression filters defined in GraphQLMeta.

    Args:
        model: Django model class

    Returns:
        Dictionary of field name to InputField mappings
    """
    fields = {}
    try:
        from ...core.meta import get_model_graphql_meta

        graphql_meta = get_model_graphql_meta(model)
        computed_defs = getattr(graphql_meta, "computed_filters", {})

        for field_name, definition in computed_defs.items():
            filter_type_name = definition.get("filter_type", "string")
            description = definition.get(
                "description", f"Filter by computed {field_name}"
            )

            input_type = FILTER_TYPE_NAME_MAP.get(
                filter_type_name.lower(), StringFilterInput
            )
            fields[field_name] = graphene.InputField(
                input_type, name=to_camel_case(field_name), description=description
            )

    except Exception as e:
        logger.debug(f"Error generating computed filters for {model.__name__}: {e}")

    return fields


def generate_array_field_filters(
    model: Type[models.Model],
) -> Dict[str, graphene.InputField]:
    """
    Generate filters for ArrayField columns (PostgreSQL).

    Args:
        model: Django model class

    Returns:
        Dictionary of field name to InputField mappings for array fields
    """
    fields = {}
    try:
        from django.contrib.postgres.fields import ArrayField

        for field in model._meta.get_fields():
            if isinstance(field, ArrayField):
                field_name = field.name
                fields[field_name] = graphene.InputField(
                    ArrayFilterInput,
                    name=to_camel_case(field_name),
                    description=f"Filter by {field_name} array field",
                )
    except ImportError:
        # PostgreSQL not available
        pass
    except Exception as e:
        logger.debug(f"Error generating array filters for {model.__name__}: {e}")

    return fields


def generate_date_trunc_filters(
    model: Type[models.Model],
    date_trunc_filter_input: Type[graphene.InputObjectType],
) -> Dict[str, graphene.InputField]:
    """
    Generate date truncation filters for date/datetime fields.

    Args:
        model: Django model class
        date_trunc_filter_input: The DateTruncFilterInput type class

    Returns:
        Dictionary of field name to InputField mappings
    """
    fields = {}

    for field in model._meta.get_fields():
        if not hasattr(field, "name"):
            continue

        if isinstance(field, (models.DateField, models.DateTimeField)):
            field_name = field.name
            trunc_field_name = f"{field_name}_trunc"
            fields[trunc_field_name] = graphene.InputField(
                date_trunc_filter_input,
                name=to_camel_case(trunc_field_name),
                description=f"Filtrer {field_name} par parties de date tronquées",
            )

    return fields


def generate_date_extract_filters(
    model: Type[models.Model],
    extract_date_filter_input: Type[graphene.InputObjectType],
) -> Dict[str, graphene.InputField]:
    """
    Generate date extraction filters for date/datetime fields.

    Unlike truncation which rounds to period boundaries, extraction pulls
    out specific components like day_of_week, hour, quarter, etc.

    Args:
        model: Django model class
        extract_date_filter_input: The ExtractDateFilterInput type class

    Returns:
        Dictionary of field name to InputField mappings
    """
    fields = {}

    for field in model._meta.get_fields():
        if not hasattr(field, "name"):
            continue

        if isinstance(field, (models.DateField, models.DateTimeField)):
            field_name = field.name
            extract_field_name = f"{field_name}_extract"
            fields[extract_field_name] = graphene.InputField(
                extract_date_filter_input,
                name=to_camel_case(extract_field_name),
                description=(
                    f"Filtrer {field_name} par parties de date extraites "
                    "(jour de la semaine, heure, etc.)"
                ),
            )

    return fields


def generate_historical_filters(
    model: Type[models.Model],
) -> Dict[str, graphene.InputField]:
    """
    Generate filters specific to django-simple-history models.

    Args:
        model: Django model class (should be a historical model)

    Returns:
        Dictionary of field name to InputField mappings
    """
    filters = {}

    # Instance filter - filter by original instance IDs
    filters["instance_in"] = graphene.InputField(
        graphene.List(graphene.NonNull(graphene.ID)),
        description="Filtrer par IDs d'instance d'origine",
    )

    # History type filter
    try:
        history_field = model._meta.get_field("history_type")
        choices = getattr(history_field, "choices", None)
        if choices:
            filters["history_type_in"] = graphene.InputField(
                graphene.List(graphene.NonNull(graphene.String)),
                description="Filtrer par type d'historique (création, mise à jour, suppression)",
            )
    except FieldDoesNotExist:
        pass

    return filters


def get_advanced_filter_types() -> Dict[str, Type[graphene.InputObjectType]]:
    """
    Lazy import of advanced filter types to avoid circular imports.

    Returns:
        Dictionary mapping type names to their corresponding classes
    """
    from .types import (
        AggregationFilterInput,
        ConditionalAggregationFilterInput,
        WindowFilterInput,
        SubqueryFilterInput,
        ExistsFilterInput,
        FieldCompareFilterInput,
        DateTruncFilterInput,
        ExtractDateFilterInput,
        FullTextSearchInput,
    )
    return {
        "AggregationFilterInput": AggregationFilterInput,
        "ConditionalAggregationFilterInput": ConditionalAggregationFilterInput,
        "WindowFilterInput": WindowFilterInput,
        "SubqueryFilterInput": SubqueryFilterInput,
        "ExistsFilterInput": ExistsFilterInput,
        "FieldCompareFilterInput": FieldCompareFilterInput,
        "DateTruncFilterInput": DateTruncFilterInput,
        "ExtractDateFilterInput": ExtractDateFilterInput,
        "FullTextSearchInput": FullTextSearchInput,
    }


__all__ = [
    # Constants
    "DEFAULT_MAX_NESTED_DEPTH",
    "MAX_ALLOWED_NESTED_DEPTH",
    "DEFAULT_CACHE_MAX_SIZE",
    "FIELD_TYPE_TO_FILTER_INPUT",
    "FILTER_TYPE_NAME_MAP",
    # Functions
    "get_filter_input_for_field",
    "is_historical_model",
    "generate_computed_filters",
    "generate_array_field_filters",
    "generate_date_trunc_filters",
    "generate_date_extract_filters",
    "generate_historical_filters",
    "get_advanced_filter_types",
]
