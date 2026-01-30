"""
Registry for custom GraphQL scalars.
"""

from typing import Optional

from .binary import Binary
from .common import URL, UUID, Decimal, Email, Phone
from .json_scalar import JSON
from .temporal import Date, DateTime, Time

# Registry of custom scalars
CUSTOM_SCALARS = {
    'DateTime': DateTime,
    'Date': Date,
    'Time': Time,
    'JSON': JSON,
    'UUID': UUID,
    'Email': Email,
    'URL': URL,
    'Phone': Phone,
    'Decimal': Decimal,
    'Binary': Binary,
}


def get_custom_scalar(scalar_name: str) -> Optional[type]:
    """
    Get custom scalar class by name.

    Args:
        scalar_name: Name of the scalar

    Returns:
        Scalar class or None if not found
    """
    return CUSTOM_SCALARS.get(scalar_name)


def register_custom_scalar(name: str, scalar_class: type) -> None:
    """
    Register a custom scalar.

    Args:
        name: Name of the scalar
        scalar_class: Scalar class
    """
    CUSTOM_SCALARS[name] = scalar_class


def get_enabled_scalars(schema_name: Optional[str] = None) -> dict:
    """
    Get enabled custom scalars for a schema.

    Args:
        schema_name: Schema name (optional)

    Returns:
        Dictionary of enabled scalars
    """
    from rail_django.config.defaults import LIBRARY_DEFAULTS

    # Get custom scalars configuration
    custom_scalars_config = LIBRARY_DEFAULTS.get("custom_scalars", {})

    enabled_scalars = {}
    for scalar_name, config in custom_scalars_config.items():
        if isinstance(config, dict) and config.get("enabled", True):
            scalar_class = get_custom_scalar(scalar_name)
            if scalar_class:
                enabled_scalars[scalar_name] = scalar_class

    return enabled_scalars
