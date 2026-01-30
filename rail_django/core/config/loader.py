"""
ConfigLoader implementation.
"""

import logging
from typing import Any, Dict, Optional

from django.conf import settings
from rail_django.config.defaults import get_merged_settings, validate_settings

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Configuration loader for rail_django settings."""

    @staticmethod
    def _normalize_legacy_sections(config: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(config, dict): return config
        normalized = dict(config)
        if "TYPE_SETTINGS" in config and "type_generation_settings" not in config:
            normalized["type_generation_settings"] = config["TYPE_SETTINGS"]
        if "PERFORMANCE" in config and "performance_settings" not in config:
            normalized["performance_settings"] = config["PERFORMANCE"]
        if "SECURITY" in config and "security_settings" not in config:
            normalized["security_settings"] = config["SECURITY"]
        return normalized

    @staticmethod
    def get_rail_django_settings() -> dict[str, Any]:
        user_settings = ConfigLoader._normalize_legacy_sections(getattr(settings, "RAIL_DJANGO_GRAPHQL", {}))
        environment = getattr(settings, "ENVIRONMENT", "development")
        return get_merged_settings(custom_settings=user_settings, environment=environment)

    @staticmethod
    def get_schema_specific_settings(schema_name: str, environment: Optional[str] = None) -> dict[str, Any]:
        if environment is None: environment = getattr(settings, "ENVIRONMENT", "development")
        user_settings = ConfigLoader._normalize_legacy_sections(getattr(settings, "RAIL_DJANGO_GRAPHQL", {}))
        return get_merged_settings(custom_settings=user_settings, schema_name=schema_name, environment=environment)

    @staticmethod
    def get_global_settings(environment: Optional[str] = None) -> dict[str, Any]:
        if environment is None: environment = getattr(settings, "ENVIRONMENT", "development")
        user_settings = ConfigLoader._normalize_legacy_sections(getattr(settings, "RAIL_DJANGO_GRAPHQL", {}))
        return get_merged_settings(custom_settings=user_settings, environment=environment)

    @staticmethod
    def get_core_schema_settings(schema_name: Optional[str] = None, environment: Optional[str] = None) -> dict[str, Any]:
        config = ConfigLoader.get_schema_specific_settings(schema_name, environment) if schema_name else ConfigLoader.get_global_settings(environment)
        return config.get("CORE_schema_settings", {})

    @staticmethod
    def get_query_settings(schema_name: Optional[str] = None, environment: Optional[str] = None) -> dict[str, Any]:
        config = ConfigLoader.get_schema_specific_settings(schema_name, environment) if schema_name else ConfigLoader.get_global_settings(environment)
        return config.get("query_settings", {})

    @staticmethod
    def get_mutation_settings(schema_name: Optional[str] = None, environment: Optional[str] = None) -> dict[str, Any]:
        config = ConfigLoader.get_schema_specific_settings(schema_name, environment) if schema_name else ConfigLoader.get_global_settings(environment)
        return config.get("mutation_settings", {})

    @staticmethod
    def get_type_generation_settings(schema_name: Optional[str] = None, environment: Optional[str] = None) -> dict[str, Any]:
        config = ConfigLoader.get_schema_specific_settings(schema_name, environment) if schema_name else ConfigLoader.get_global_settings(environment)
        return config.get("type_generation_settings", {})

    @staticmethod
    def get_performance_settings(schema_name: Optional[str] = None, environment: Optional[str] = None) -> dict[str, Any]:
        config = ConfigLoader.get_schema_specific_settings(schema_name, environment) if schema_name else ConfigLoader.get_global_settings(environment)
        return config.get("performance_settings", config.get("PERFORMANCE", {}))

    @staticmethod
    def get_security_settings(schema_name: Optional[str] = None, environment: Optional[str] = None) -> dict[str, Any]:
        config = ConfigLoader.get_schema_specific_settings(schema_name, environment) if schema_name else ConfigLoader.get_global_settings(environment)
        return config.get("security_settings", config.get("SECURITY", {}))

    @staticmethod
    def validate_configuration(config: Optional[dict[str, Any]] = None, schema_name: Optional[str] = None, environment: Optional[str] = None) -> bool:
        try:
            if config is None:
                config = ConfigLoader.get_schema_specific_settings(schema_name, environment) if schema_name else ConfigLoader.get_rail_django_settings()
            validate_settings(config); return True
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}"); return False

    @staticmethod
    def debug_configuration(schema_name: Optional[str] = None, environment: Optional[str] = None) -> None:
        if schema_name:
            config = ConfigLoader.get_schema_specific_settings(schema_name, environment)
            print(f"=== Schema '{schema_name}' Configuration Debug ===")
        else:
            config = ConfigLoader.get_rail_django_settings()
            print("=== Global rail_django Configuration Debug ===")
        print(f"Environment: {environment or getattr(settings, 'ENVIRONMENT', 'development')}")
        print(f"Full config keys: {list(config.keys())}")
        sections = ["CORE_schema_settings", "query_settings", "mutation_settings", "subscription_settings", "type_generation_settings", "performance_settings", "security_settings", "ERROR_HANDLING_SETTINGS", "CACHING_SETTINGS", "FILE_UPLOAD_SETTINGS", "MONITORING_SETTINGS", "DEVELOPMENT_SETTINGS", "SCHEMA_REGISTRY_SETTINGS", "MIDDLEWARE_SETTINGS", "EXTENSION_SETTINGS", "INTERNATIONALIZATION_SETTINGS", "TESTING_SETTINGS"]
        for s in sections: print(f"{s}: {len(config[s]) if s in config else 'not found'}")
        print("=== End Configuration Debug ===")
