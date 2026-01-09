"""
Plugin architecture for GraphQL schema registry.

This module provides a plugin system that allows extending the schema registry
functionality through hooks and plugins.
"""

from .base import BasePlugin, PluginManager
from .hooks import HookRegistry

__all__ = ['BasePlugin', 'PluginManager', 'HookRegistry']
