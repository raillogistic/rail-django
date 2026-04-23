"""
Plugin architecture for GraphQL schema registry.

This module provides a plugin system that allows extending the schema registry
functionality through hooks and plugins.
"""

from .base import BasePlugin, ExecutionHookResult, PluginManager, plugin_manager
from .hooks import HookRegistry, hook_registry

__all__ = [
    "BasePlugin",
    "ExecutionHookResult",
    "PluginManager",
    "plugin_manager",
    "HookRegistry",
    "hook_registry",
]
