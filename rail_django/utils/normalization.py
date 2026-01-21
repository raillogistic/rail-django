"""
Normalization utilities for Rail Django.

This module provides functions for normalizing configuration values,
lists, and other data structures used throughout the framework.
"""

from typing import Any, Dict, Iterable, List, Optional


def normalize_list(values: Iterable[Any]) -> List[str]:
    """
    Normalize an iterable to a list of lowercase strings.

    Args:
        values: Iterable of values to normalize.

    Returns:
        List of lowercase strings.

    Examples:
        >>> normalize_list(["Product", "ORDER", "user"])
        ["product", "order", "user"]
    """
    if not values:
        return []
    return [str(v).lower() for v in values if v is not None]


def normalize_string_list(values: Iterable[Any]) -> List[str]:
    """
    Normalize an iterable to a list of strings (preserving case).

    Args:
        values: Iterable of values to normalize.

    Returns:
        List of strings.

    Examples:
        >>> normalize_string_list(["Product", 123, None])
        ["Product", "123"]
    """
    if not values:
        return []
    return [str(v) for v in values if v is not None]


def normalize_accessor(value: str) -> str:
    """
    Normalize a field accessor string.

    Args:
        value: Field accessor like "user__profile__name".

    Returns:
        Normalized accessor string.

    Examples:
        >>> normalize_accessor("  user__profile__name  ")
        "user__profile__name"
    """
    if not value:
        return ""
    return value.strip().replace(" ", "")


def normalize_header_key(header_name: str) -> str:
    """
    Normalize an HTTP header name.

    Args:
        header_name: Header name to normalize.

    Returns:
        Normalized header name in lowercase with underscores.

    Examples:
        >>> normalize_header_key("X-Tenant-ID")
        "x_tenant_id"
    """
    if not header_name:
        return ""
    return header_name.lower().replace("-", "_")


def normalize_legacy_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize legacy configuration format to current format.

    Args:
        config: Configuration dictionary.

    Returns:
        Normalized configuration dictionary.
    """
    if not config:
        return {}

    result = dict(config)

    # Map legacy keys to new keys
    legacy_mappings = {
        "GRAPHQL": "SCHEMA",
        "AUTO_CAMELCASE": "auto_camelcase",
        "DEPTH_LIMIT": "depth_limit",
        "ENABLE_INTROSPECTION": "introspection",
    }

    for old_key, new_key in legacy_mappings.items():
        if old_key in result and new_key not in result:
            result[new_key] = result.pop(old_key)

    return result


def normalize_model_label(value: Any) -> Optional[str]:
    """
    Normalize a model label to consistent format.

    Args:
        value: Model class, string label, or None.

    Returns:
        Normalized model label like "app_label.ModelName" or None.

    Examples:
        >>> normalize_model_label("myapp.MyModel")
        "myapp.MyModel"
        >>> normalize_model_label(MyModel)
        "myapp.MyModel"
    """
    if value is None:
        return None

    if isinstance(value, str):
        return value

    # Check if it's a Django model class
    if hasattr(value, "_meta"):
        meta = value._meta
        return f"{meta.app_label}.{meta.object_name}"

    return str(value)


def normalize_dict_keys(data: Dict[str, Any], lowercase: bool = True) -> Dict[str, Any]:
    """
    Normalize dictionary keys.

    Args:
        data: Dictionary to normalize.
        lowercase: Whether to lowercase keys.

    Returns:
        Dictionary with normalized keys.

    Examples:
        >>> normalize_dict_keys({"FirstName": "John", "LAST_NAME": "Doe"})
        {"firstname": "John", "last_name": "Doe"}
    """
    if not data:
        return {}

    if lowercase:
        return {k.lower(): v for k, v in data.items()}
    return dict(data)


def normalize_filter_value(value: str) -> str:
    """
    Normalize a filter value string.

    Args:
        value: Filter value to normalize.

    Returns:
        Normalized filter value.

    Examples:
        >>> normalize_filter_value("  status__exact  ")
        "status__exact"
    """
    if not value:
        return ""
    return value.strip()


def normalize_ordering(ordering: Optional[Iterable[str]]) -> List[str]:
    """
    Normalize ordering specification.

    Args:
        ordering: Ordering fields (with optional - prefix).

    Returns:
        Normalized list of ordering fields.

    Examples:
        >>> normalize_ordering(["-created_at", "  name  "])
        ["-created_at", "name"]
    """
    if not ordering:
        return []
    return [o.strip() for o in ordering if o and o.strip()]
