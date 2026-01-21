"""
Configuration helpers.
"""

import logging
from typing import Any, Optional, TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from ..settings import MutationGeneratorSettings, TypeGeneratorSettings, SchemaSettings

logger = logging.getLogger(__name__)


def load_mutation_settings_from_config(config: dict[str, Any]) -> Optional["MutationGeneratorSettings"]:
    try:
        from ..settings import MutationGeneratorSettings
        return MutationGeneratorSettings.from_dict(config)
    except ImportError: return None


def load_type_settings_from_config(config: dict[str, Any]) -> Optional["TypeGeneratorSettings"]:
    try:
        from ..settings import TypeGeneratorSettings
        return TypeGeneratorSettings.from_dict(config)
    except ImportError: return None


def load_schema_settings_from_config(config: dict[str, Any]) -> Optional["SchemaSettings"]:
    try:
        from ..settings import SchemaSettings
        return SchemaSettings.from_dict(config)
    except ImportError: return None


def get_setting_value(key: str, default: Any = None, schema_name: Optional[str] = None, environment: Optional[str] = None) -> Any:
    """Get a specific setting value with hierarchical lookup."""
    try:
        from .loader import ConfigLoader
        config = ConfigLoader.get_schema_specific_settings(schema_name, environment) if schema_name else ConfigLoader.get_rail_django_settings()
        if "." in key:
            value = config
            for k in key.split("."):
                if isinstance(value, dict) and k in value: value = value[k]
                else: return default
            return value
        return config.get(key, default)
    except Exception as e:
        logger.warning(f"Error getting setting '{key}': {e}"); return default
