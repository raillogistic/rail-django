"""Core public API for Rail Django.

Keep this package import-light. Callers often import ``rail_django.core`` or
reach these symbols through the top-level package before Django settings are
configured, so heavy framework imports must stay lazy.
"""

from importlib import import_module

_LAZY_EXPORTS = {
    "ConfigLoader": ("rail_django.core.config", "ConfigLoader"),
    "SchemaBuilder": ("rail_django.core.schema", "SchemaBuilder"),
    "TypeGeneratorSettings": ("rail_django.core.settings", "TypeGeneratorSettings"),
    "QueryGeneratorSettings": ("rail_django.core.settings", "QueryGeneratorSettings"),
    "MutationGeneratorSettings": (
        "rail_django.core.settings",
        "MutationGeneratorSettings",
    ),
    "SchemaSettings": ("rail_django.core.settings", "SchemaSettings"),
    "GraphQLAutoConfig": ("rail_django.core.settings", "GraphQLAutoConfig"),
    "FilteringSettings": ("rail_django.core.settings", "FilteringSettings"),
    "GraphQLAutoError": ("rail_django.core.exceptions", "GraphQLAutoError"),
    "ValidationError": ("rail_django.core.exceptions", "ValidationError"),
    "AuthenticationError": ("rail_django.core.exceptions", "AuthenticationError"),
    "PermissionError": ("rail_django.core.exceptions", "PermissionError"),
    "ResourceNotFoundError": (
        "rail_django.core.exceptions",
        "ResourceNotFoundError",
    ),
    "SecurityError": ("rail_django.core.exceptions", "SecurityError"),
    "RateLimitError": ("rail_django.core.exceptions", "RateLimitError"),
    "QueryComplexityError": ("rail_django.core.exceptions", "QueryComplexityError"),
    "QueryDepthError": ("rail_django.core.exceptions", "QueryDepthError"),
    "FileUploadError": ("rail_django.core.exceptions", "FileUploadError"),
    "ErrorCode": ("rail_django.core.exceptions", "ErrorCode"),
    "ErrorHandler": ("rail_django.core.exceptions", "ErrorHandler"),
    "error_handler": ("rail_django.core.exceptions", "error_handler"),
    "handle_graphql_error": ("rail_django.core.exceptions", "handle_graphql_error"),
    "RequestMetrics": ("rail_django.middleware.performance", "RequestMetrics"),
    "PerformanceAlert": ("rail_django.middleware.performance", "PerformanceAlert"),
    "PerformanceAggregator": (
        "rail_django.middleware.performance",
        "PerformanceAggregator",
    ),
    "GraphQLPerformanceMiddleware": (
        "rail_django.middleware.performance",
        "GraphQLPerformanceMiddleware",
    ),
    "GraphQLPerformanceView": (
        "rail_django.middleware.performance",
        "GraphQLPerformanceView",
    ),
    "get_performance_aggregator": (
        "rail_django.middleware.performance",
        "get_performance_aggregator",
    ),
    "setup_performance_monitoring": (
        "rail_django.middleware.performance",
        "setup_performance_monitoring",
    ),
    "monitor_performance": (
        "rail_django.middleware.performance",
        "monitor_performance",
    ),
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name):
    """Resolve exported symbols lazily to avoid import-time side effects."""
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'") from exc

    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Include lazily exported symbols in interactive discovery."""
    return sorted(set(globals()) | set(__all__))
