"""
Shared utility functions for mutation pipeline steps.

These functions are extracted from the original mutations_crud.py to eliminate
code duplication and provide reusable building blocks for pipeline steps.
"""

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from django.db import models


def sanitize_input_data(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize input data to handle special characters.

    - Converts ID to string if present (handles UUID objects)
    - Handles double quote escaping
    - Recursively processes nested structures

    Args:
        input_data: The input data to sanitize

    Returns:
        Dict with sanitized data
    """
    result = input_data.copy()

    if "id" in result and not isinstance(result["id"], str):
        result["id"] = str(result["id"])

    def sanitize_value(value):
        if isinstance(value, str):
            # Handle double quotes by escaping them properly
            return value.replace('""', '"')
        if isinstance(value, dict):
            return {k: sanitize_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [sanitize_value(item) for item in value]
        return value

    return {k: sanitize_value(v) for k, v in result.items()}


def normalize_enum_inputs(
    input_data: dict[str, Any], model: type["models.Model"]
) -> dict[str, Any]:
    """
    Normalize GraphQL Enum inputs to their underlying Django field values.

    GraphQL enums come through as objects with a 'value' attribute.
    This function extracts the underlying values for storage in Django.

    Args:
        input_data: Input payload from GraphQL mutation
        model: Django model being mutated

    Returns:
        Dict with enum values normalized to their underlying values

    Example:
        >>> normalized = normalize_enum_inputs({'status': StatusEnum.ACTIVE}, Book)
        >>> isinstance(normalized['status'], str)
        True
    """
    normalized = input_data.copy()

    # Build mapping of choice fields for the model
    choice_fields = {
        f.name: f
        for f in model._meta.get_fields()
        if hasattr(f, "choices") and getattr(f, "choices", None)
    }

    def normalize_value(value: Any) -> Any:
        # Graphene enum may come through as an object with a 'value' attribute
        if hasattr(value, "value") and not isinstance(value, (str, bytes)):
            try:
                return getattr(value, "value")
            except Exception:
                return value
        # Recurse into lists/dicts for nested structures
        if isinstance(value, list):
            return [normalize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: normalize_value(v) for k, v in value.items()}
        return value

    for field_name in choice_fields:
        if field_name in normalized:
            normalized[field_name] = normalize_value(normalized[field_name])

    return normalized


def process_relation_operations(
    input_data: dict[str, Any],
    model: type["models.Model"],
    introspector=None,
) -> dict[str, Any]:
    """
    Process unified relation inputs.
    Validates structure of relation operations.

    Args:
        input_data: The input data to process
        model: The Django model
        introspector: Optional ModelIntrospector instance

    Returns:
        Dict with validated relation operations

    Raises:
        ValidationError: If operation constraints are violated
    """
    from django.core.exceptions import ValidationError
    from rail_django.generators.introspector import ModelIntrospector

    if introspector is None:
        introspector = ModelIntrospector.for_model(model)

    processed = input_data.copy()
    relationships = introspector.get_model_relationships()
    reverse_relations = introspector.get_reverse_relations()
    
    # Merge relationships and reverse relations for checking
    # Note: reverse_relations values are dicts or objects depending on implementation
    all_relations = {}
    for k, v in relationships.items():
        all_relations[k] = v
    for k, v in reverse_relations.items():
        all_relations[k] = v

    for field_name, value in processed.items():
        if field_name not in all_relations:
            continue
            
        if not isinstance(value, dict):
            continue
            
        rel_info = all_relations[field_name]
        is_list = False
        
        # Check if relation is list-based (M2M or Reverse)
        if isinstance(rel_info, dict): # Reverse relation usually
             is_list = True
        elif hasattr(rel_info, "relationship_type") and rel_info.relationship_type == "ManyToManyField":
             is_list = True
             
        ops = set(value.keys())
        
        if not is_list:
            # FK/OneToOne: Only ONE operation allowed (connect, create, OR update)
            count = sum(1 for op in ["connect", "create", "update"] if op in value)
            if count > 1:
                raise ValidationError({
                    field_name: f"For singular relation '{field_name}', provide exactly one of: connect, create, update."
                })
        else:
            # M2M/Reverse: 'set' cannot combine with others
            if "set" in value and (len(ops) > 1):
                 raise ValidationError({
                    field_name: f"For relation '{field_name}', 'set' cannot be combined with other operations."
                })

    return processed


def get_mandatory_fields(
    model: type["models.Model"], graphql_meta=None
) -> list[str]:
    """
    Get mandatory fields from model's GraphQLMeta configuration.

    Args:
        model: The Django model
        graphql_meta: Optional GraphQLMeta instance

    Returns:
        List of field names that are mandatory
    """
    if graphql_meta is None:
        from ..core.meta import get_model_graphql_meta

        graphql_meta = get_model_graphql_meta(model)

    # Read from GraphQLMeta configuration
    field_config = getattr(graphql_meta, "field_config", None)
    if field_config:
        mandatory = getattr(field_config, "mandatory", None)
        if mandatory:
            return list(mandatory)

    # Fallback: derive from model field definitions
    mandatory = []
    for field in model._meta.get_fields():
        if hasattr(field, "null") and hasattr(field, "blank"):
            # Check if field is required (not null, not blank, no default)
            if not field.null and not field.blank:
                has_default = getattr(field, "has_default", lambda: False)
                if callable(has_default):
                    has_default = has_default()
                if not has_default:
                    # Only include relationship fields
                    if hasattr(field, "remote_field") and field.remote_field:
                        mandatory.append(field.name)

    return mandatory


def filter_read_only_fields(
    input_data: dict[str, Any], graphql_meta
) -> dict[str, Any]:
    """
    Remove read-only fields from input data.

    Args:
        input_data: The input data to filter
        graphql_meta: GraphQLMeta instance with field_config

    Returns:
        Dict with read-only fields removed
    """
    if graphql_meta is None:
        return input_data

    field_config = getattr(graphql_meta, "field_config", None)
    if not field_config:
        return input_data

    read_only = set(getattr(field_config, "read_only", []) or [])
    if not read_only:
        return input_data

    return {k: v for k, v in input_data.items() if k not in read_only}


def auto_populate_created_by(
    input_data: dict[str, Any],
    model: type["models.Model"],
    user,
) -> dict[str, Any]:
    """
    Auto-populate created_by field if available on model.

    Args:
        input_data: The input data to update
        model: The Django model
        user: The authenticated user

    Returns:
        Dict with created_by populated if applicable
    """
    if "created_by" in input_data or "created_by_id" in input_data:
        return input_data

    try:
        field = model._meta.get_field("created_by")
        if user and getattr(user, "is_authenticated", False) and field:
            result = input_data.copy()
            # Assign FK id directly to avoid requiring nested relation
            # permission checks on the related User retrieve operation.
            result["created_by_id"] = user.id
            return result
    except Exception:
        pass

    return input_data


def decode_global_id(id_value: str) -> tuple[Optional[str], str]:
    """
    Decode a potentially encoded GraphQL global ID.

    Args:
        id_value: The ID to decode

    Returns:
        Tuple of (type_name or None, decoded_id)
    """
    try:
        from graphql_relay import from_global_id

        type_name, decoded_id = from_global_id(id_value)
        # If decoding resulted in empty values, the input wasn't a valid global ID
        if not decoded_id:
            return None, id_value
        return type_name, decoded_id
    except Exception:
        return None, id_value
