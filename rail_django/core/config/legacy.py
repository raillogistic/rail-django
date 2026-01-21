"""
Legacy configuration support.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

def get_rail_django_settings_legacy() -> dict[str, Any]:
    from .loader import ConfigLoader
    return ConfigLoader.get_rail_django_settings()


def validate_configuration_legacy() -> bool:
    try: return isinstance(get_rail_django_settings_legacy(), dict)
    except Exception as e:
        logger.error(f"Legacy configuration validation failed: {e}"); return False


def debug_configuration_legacy() -> None:
    config = get_rail_django_settings_legacy()
    print("=== Legacy rail_django Configuration Debug ===")
    print(f"Full legacy config: {config}")
    for section in ["mutation_settings", "subscription_settings", "TYPE_SETTINGS", "schema_settings"]:
        print(f"{section} found: {config[section]}" if section in config else f"{section} not found")
    print("=== End Legacy Configuration Debug ===")
