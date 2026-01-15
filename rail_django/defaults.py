"""
Default configuration for the rail-django library.

The goal of this module is to expose a single source of truth for every
setting that the library actually consumes. Each section mirrors one of the
dataclasses defined in ``rail_django.core.settings`` or a concrete
settings block consumed by the runtime (security, middleware, performance,
etc.).
"""

from __future__ import annotations

from typing import Any, Dict, List

LIBRARY_VERSION = "1.0.0"
LIBRARY_NAME = "rail-django"


# --------------------------------------------------------------------------- #
# Library-wide defaults (grouped by feature area)
# --------------------------------------------------------------------------- #
LIBRARY_DEFAULTS: dict[str, Any] = {
    "schema_settings": {
        "excluded_apps": [],
        "excluded_models": [],
        "enable_introspection": True,
        "enable_graphiql": True,
        "auto_refresh_on_model_change": False,
        "auto_refresh_on_migration": True,
        "prebuild_on_startup": True,
        "authentication_required": False,
        "enable_pagination": True,
        "auto_camelcase": False,
        "disable_security_mutations": False,
        "enable_extension_mutations": True,
        "show_metadata": False,
        "query_extensions": [],
        "mutation_extensions": [],
        "query_field_allowlist": None,
        "mutation_field_allowlist": None,
        "subscription_field_allowlist": None,
    },
    "type_generation_settings": {
        "exclude_fields": {},
        "excluded_fields": {},
        "include_fields": None,
        "custom_field_mappings": {},
        "generate_filters": True,
        "enable_filtering": True,
        "auto_camelcase": False,
        "generate_descriptions": True,
    },
    "query_settings": {
        "generate_filters": True,
        "generate_ordering": True,
        "generate_pagination": True,
        "enable_pagination": True,
        "enable_ordering": True,
        "use_relay": False,
        "default_page_size": 20,
        "max_page_size": 100,
        "max_property_ordering_results": 2000,
        "property_ordering_warn_on_cap": True,
        "additional_lookup_fields": {},
    },
    "mutation_settings": {
        "generate_create": True,
        "generate_update": True,
        "generate_delete": True,
        "generate_bulk": False,
        "enable_create": True,
        "enable_update": True,
        "enable_delete": True,
        "enable_bulk_operations": False,
        "enable_method_mutations": True,
        "bulk_batch_size": 100,
        "required_update_fields": {},
        "enable_nested_relations": True,
        "nested_relations_config": {},
        "nested_field_config": {},
    },
    "subscription_settings": {
        "enable_subscriptions": True,
        "enable_create": True,
        "enable_update": True,
        "enable_delete": True,
        "enable_filters": True,
        "include_models": [],
        "exclude_models": [],
    },
    "performance_settings": {
        "enable_query_optimization": True,
        "enable_select_related": True,
        "enable_prefetch_related": True,
        "enable_only_fields": True,
        "enable_defer_fields": False,
        "enable_dataloader": True,
        "dataloader_batch_size": 100,
        "max_prefetch_depth": 3,
        "max_query_depth": 10,
        "max_query_complexity": 1000,
        "enable_query_cost_analysis": False,
        "query_timeout": 30,
        "enable_query_metrics": True,
        "enable_n_plus_one_detection": True,
        "n_plus_one_threshold": 5,
        "enable_query_caching": False,
        "query_cache_timeout": 300,
        "query_cache_user_specific": False,
        "query_cache_scope": "schema",
    },
    "persisted_query_settings": {
        "enabled": False,
        "cache_alias": "default",
        "ttl": 86400,
        "allow_unregistered": True,
        "enforce_allowlist": False,
        "allowlist": {},
        "allowlist_path": None,
        "hash_algorithm": "sha256",
        "max_query_length": 0,
    },
    "security_settings": {
        "enable_authentication": True,
        "enable_authorization": True,
        "enable_policy_engine": True,
        "enable_permission_cache": True,
        "permission_cache_ttl_seconds": 300,
        "enable_permission_audit": False,
        "permission_audit_log_all": False,
        "permission_audit_log_denies": True,
        "enable_rate_limiting": False,
        "rate_limit_requests_per_minute": 60,
        "rate_limit_requests_per_hour": 1000,
        "enable_query_depth_limiting": True,
        "introspection_roles": ["admin", "developer"],
        # "max_query_depth": 10,  # Unused: This is controlled by performance_settings.max_query_depth
        # "enable_introspection": True,  # Unused: Controlled by schema_settings.enable_introspection
        # "enable_graphiql": True,  # Unused: Controlled by schema_settings.enable_graphiql
        "allowed_origins": ["*"],
        "enable_csrf_protection": True,
        "enable_cors": True,
        "enable_field_permissions": True,
        "enable_object_permissions": True,
        "enable_input_validation": True,
        "enable_sql_injection_protection": True,
        "enable_xss_protection": True,
        "field_permission_input_mode": "reject",
        "input_allow_html": False,
        "input_allowed_html_tags": [
            "p",
            "br",
            "strong",
            "em",
            "u",
            "ol",
            "ul",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "blockquote",
        ],
        "input_allowed_html_attributes": {
            "*": ["class"],
            "a": ["href", "title"],
            "img": ["src", "alt", "width", "height"],
        },
        "input_max_string_length": None,
        "input_truncate_long_strings": False,
        "input_failure_severity": "high",
        "input_pattern_scan_limit": 10000,
        "session_timeout_minutes": 30,
        "max_file_upload_size": 10 * 1024 * 1024,
        "allowed_file_types": [".jpg", ".jpeg", ".png", ".pdf", ".txt"],
    },
    "middleware_settings": {
        "enable_authentication_middleware": True,
        "enable_logging_middleware": True,
        "enable_performance_middleware": True,
        "enable_error_handling_middleware": True,
        "enable_rate_limiting_middleware": True,
        "enable_validation_middleware": True,
        "enable_field_permission_middleware": True,
        "enable_cors_middleware": True,
        "log_queries": True,
        "log_mutations": True,
        "log_introspection": False,
        "log_errors": True,
        "log_performance": True,
        "performance_threshold_ms": 1000,
        "enable_query_complexity_middleware": True,
    },
    "plugin_settings": {
        "enable_schema_hooks": True,
        "enable_execution_hooks": True,
    },
    "webhook_settings": {
        "enabled": False,
        "endpoints": [],
        "events": {"created": True, "updated": True, "deleted": True},
        "include_models": [],
        "exclude_models": [],
        "include_fields": {},
        "exclude_fields": {},
        "redact_fields": [],
        "redaction_mask": "***REDACTED***",
        "headers": {},
        "timeout_seconds": 5,
        "signing_secret": None,
        "signing_header": "X-Rail-Signature",
        "signature_prefix": "sha256=",
        "event_header": "X-Rail-Event",
        "id_header": "X-Rail-Event-Id",
        "auth_header": "Authorization",
        "auth_scheme": "Bearer",
        "auth_token_path": None,
        "auth_url": None,
        "auth_payload": {},
        "auth_headers": {},
        "auth_timeout_seconds": 5,
        "auth_token_field": "access_token",
        "async_backend": "thread",
        "async_task_path": None,
        "max_workers": 4,
        "max_retries": 3,
        "retry_backoff_seconds": 2,
        "retry_backoff_factor": 2,
        "retry_jitter_seconds": 0.5,
        "retry_statuses": [429, 500, 502, 503, 504],
    },
    "error_handling": {
        "enable_detailed_errors": False,
        "enable_error_logging": True,
        "enable_error_reporting": True,
        "enable_sentry_integration": False,
        "mask_internal_errors": True,
        "include_stack_trace": False,
        "error_code_prefix": "RAIL_GQL",
        "max_error_message_length": 500,
        "enable_error_categorization": True,
        "enable_error_metrics": True,
        "log_level": "ERROR",
    },
    "custom_scalars": {
        "DateTime": {"enabled": True},
        "Date": {"enabled": True},
        "Time": {"enabled": True},
        "JSON": {"enabled": True},
        "UUID": {"enabled": True},
        "Email": {"enabled": True},
        "URL": {"enabled": True},
        "Phone": {"enabled": True},
        "Decimal": {"enabled": True},
        "Binary": {"enabled": True},
    },
    "monitoring_settings": {
        "enable_metrics": False,
        "metrics_backend": "prometheus",
    },
    "schema_registry": {
        "enable_registry": False,
        "auto_discover_packages": [],
        "enable_schema_snapshots": False,
        "snapshot_max_entries": 50,
        "enable_schema_export": True,
        "enable_schema_diff": True,
    },
}


# --------------------------------------------------------------------------- #
# Schema / environment overrides (kept minimal & optional)
# --------------------------------------------------------------------------- #
SCHEMA_DEFAULTS: dict[str, dict[str, Any]] = {}

ENVIRONMENT_DEFAULTS: dict[str, dict[str, Any]] = {
    "development": {
        "schema_settings": {
            "enable_graphiql": True,
            "enable_introspection": True,
        }
    },
    "testing": {
        "schema_settings": {
            "enable_graphiql": False,
            "enable_introspection": True,
        }
    },
    "production": {
        "schema_settings": {
            "enable_graphiql": False,
            "enable_introspection": False,
        }
    },
}


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #
def get_default_settings() -> dict[str, Any]:
    """Return a shallow copy of the library defaults."""
    return LIBRARY_DEFAULTS.copy()


def get_schema_defaults(schema_name: str) -> dict[str, Any]:
    """Return schema-specific overrides if any were defined."""
    return SCHEMA_DEFAULTS.get(schema_name, {}).copy()


def get_environment_defaults(environment: str) -> dict[str, Any]:
    """Return environment-specific overrides."""
    return ENVIRONMENT_DEFAULTS.get(environment, {}).copy()


def merge_settings(*settings_dicts: dict[str, Any]) -> dict[str, Any]:
    """
    Merge multiple settings dictionaries with deep merging for nested dicts.
    Later dictionaries override earlier ones.
    """
    result: dict[str, Any] = {}
    for settings_dict in settings_dicts:
        for key, value in settings_dict.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = merge_settings(result[key], value)
            else:
                result[key] = value
    return result


def get_merged_settings(
    schema_name: str | None = None,
    environment: str | None = None,
    custom_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Merge defaults + environment overrides + schema overrides + custom settings.
    Priority (lowest to highest):
        1. library defaults
        2. environment defaults
        3. schema defaults
        4. custom settings
    """
    settings_to_merge: list[dict[str, Any]] = [get_default_settings()]

    if environment:
        env_defaults = get_environment_defaults(environment)
        if env_defaults:
            settings_to_merge.append(env_defaults)

    if schema_name:
        schema_defaults = get_schema_defaults(schema_name)
        if schema_defaults:
            settings_to_merge.append(schema_defaults)

    if custom_settings:
        settings_to_merge.append(custom_settings)

    return merge_settings(*settings_to_merge)


def validate_settings(settings: dict[str, Any]) -> list[str]:
    """
    Validate a settings dictionary and return a list of validation errors.
    """
    errors: list[str] = []

    required_sections = ["schema_settings", "query_settings", "mutation_settings"]
    for section in required_sections:
        if section not in settings:
            errors.append(f"Required setting '{section}' is missing")

    query_settings = settings.get("query_settings", {})
    default_page_size = query_settings.get("default_page_size")
    max_page_size = query_settings.get("max_page_size")

    if default_page_size is not None and default_page_size <= 0:
        errors.append("query_settings.default_page_size must be greater than 0")
    if max_page_size is not None and max_page_size <= 0:
        errors.append("query_settings.max_page_size must be greater than 0")
    if default_page_size and max_page_size and default_page_size > max_page_size:
        errors.append(
            "query_settings.default_page_size cannot be greater than max_page_size"
        )

    return errors
