"""
Plugin middleware for Rail Django GraphQL.

This module provides middleware for plugin execution hooks and CORS
handling for GraphQL operations.
"""

import logging
from typing import Any, Callable, Optional

from .base import BaseMiddleware
from ...config_proxy import get_setting
from ...plugins.base import plugin_manager

logger = logging.getLogger(__name__)


class PluginMiddleware(BaseMiddleware):
    """Middleware for plugin execution hooks.

    This middleware integrates with the plugin system to run hooks
    before and after GraphQL operations and field resolutions.
    """

    def __init__(self, schema_name: Optional[str] = None):
        """Initialize plugin middleware.

        Args:
            schema_name: Optional schema name for schema-specific plugins.
        """
        super().__init__(schema_name)
        self.enabled = bool(
            get_setting("plugin_settings.enable_execution_hooks", True, schema_name)
        )

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Execute plugin hooks around field resolution.

        Args:
            next_resolver: Next resolver in the chain.
            root: Root value.
            info: GraphQL resolve info.
            **kwargs: Additional arguments.

        Returns:
            Resolver result, potentially modified by plugins.
        """
        if not self.enabled:
            return next_resolver(root, info, **kwargs)

        schema_name = getattr(info.context, "schema_name", None) or self.schema_name
        operation_type = info.operation.operation.value if info.operation else "unknown"
        operation_name = self._get_operation_name(info)
        context = self._get_plugin_context(info)
        is_root = self._is_root_field(info)

        if is_root:
            decision = plugin_manager.run_before_operation(
                schema_name, operation_type, operation_name, info, context
            )
            if decision and decision.handled:
                return decision.result

        decision = plugin_manager.run_before_resolve(
            schema_name, info, root, kwargs, context
        )
        if decision and decision.handled:
            return decision.result

        try:
            result = next_resolver(root, info, **kwargs)
        except Exception as exc:
            plugin_manager.run_after_resolve(
                schema_name, info, root, kwargs, None, exc, context
            )
            if is_root:
                plugin_manager.run_after_operation(
                    schema_name, operation_type, operation_name, info, None, exc, context
                )
            raise

        after_resolve = plugin_manager.run_after_resolve(
            schema_name, info, root, kwargs, result, None, context
        )
        if after_resolve and after_resolve.handled:
            result = after_resolve.result

        if is_root:
            after_operation = plugin_manager.run_after_operation(
                schema_name, operation_type, operation_name, info, result, None, context
            )
            if after_operation and after_operation.handled:
                result = after_operation.result

        return result

    @staticmethod
    def _get_plugin_context(info: Any) -> dict[str, Any]:
        """Get or create the plugin context for this request."""
        context = getattr(info.context, "_rail_plugin_context", None)
        if context is None:
            context = {}
            setattr(info.context, "_rail_plugin_context", context)
        return context

    @staticmethod
    def _is_root_field(info: Any) -> bool:
        """Check if this is a root field resolution."""
        path = getattr(info, "path", None)
        if path is None:
            return True
        return getattr(path, "prev", None) is None

    @staticmethod
    def _get_operation_name(info: Any) -> Optional[str]:
        """Get the operation name from the info object."""
        operation = getattr(info, "operation", None)
        name_node = getattr(operation, "name", None)
        if name_node and getattr(name_node, "value", None):
            return name_node.value
        return None


class CORSMiddleware(BaseMiddleware):
    """Middleware for CORS handling.

    This middleware provides CORS-related logic for GraphQL requests.
    Note that CORS headers are typically handled at the HTTP level,
    but this middleware can add additional CORS-related logic if needed.
    """

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Handle CORS for GraphQL requests.

        Args:
            next_resolver: Next resolver in the chain.
            root: Root value.
            info: GraphQL resolve info.
            **kwargs: Additional arguments.

        Returns:
            Resolver result.
        """
        if not self.settings.enable_cors_middleware:
            return next_resolver(root, info, **kwargs)

        # CORS headers are typically handled at the HTTP level
        # This middleware can add additional CORS-related logic if needed

        return next_resolver(root, info, **kwargs)
