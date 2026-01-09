"""
Base plugin architecture for GraphQL schema registry.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from django.conf import settings

logger = logging.getLogger(__name__)


class BasePlugin(ABC):
    """
    Base class for all schema registry plugins.

    Plugins can extend the functionality of the schema registry by:
    - Adding custom discovery logic
    - Modifying schema registration parameters
    - Performing actions after schema registration
    - Adding custom validation
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the plugin.

        Args:
            config: Plugin configuration dictionary
        """
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        self.name = self.__class__.__name__

    @abstractmethod
    def get_name(self) -> str:
        """Return the plugin name."""
        return self.name

    def get_version(self) -> str:
        """Return the plugin version."""
        return getattr(self, 'VERSION', '1.0.0')

    def is_enabled(self) -> bool:
        """Check if plugin is enabled."""
        return self.enabled

    def pre_registration_hook(self, registry, schema_name: str, **kwargs) -> Dict[str, Any]:
        """
        Hook called before schema registration.

        Args:
            registry: Schema registry instance
            schema_name: Name of schema being registered
            **kwargs: Registration parameters

        Returns:
            Modified registration parameters
        """
        return kwargs

    def post_registration_hook(self, registry, schema_info) -> None:
        """
        Hook called after schema registration.

        Args:
            registry: Schema registry instance
            schema_info: Registered schema information
        """
        pass

    def discovery_hook(self, registry) -> None:
        """
        Hook called during schema discovery.

        Args:
            registry: Schema registry instance
        """
        pass

    def validate_schema(self, schema_info) -> List[str]:
        """
        Validate a schema and return list of errors.

        Args:
            schema_info: Schema information to validate

        Returns:
            List of validation error messages
        """
        return []


class PluginManager:
    """
    Manages plugins for the schema registry.
    """

    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}
        self._loaded = False

    def load_plugins(self) -> None:
        """Load plugins from Django settings."""
        if self._loaded:
            return

        plugin_configs = getattr(settings, 'GRAPHQL_SCHEMA_PLUGINS', {})

        for plugin_path, config in plugin_configs.items():
            try:
                self.load_plugin(plugin_path, config)
            except Exception as e:
                logger.error(f"Failed to load plugin '{plugin_path}': {e}")

        self._loaded = True
        logger.info(f"Loaded {len(self._plugins)} plugins")

    def load_plugin(self, plugin_path: str, config: Dict[str, Any]) -> None:
        """
        Load a single plugin.

        Args:
            plugin_path: Python path to plugin class
            config: Plugin configuration
        """
        try:
            module_path, class_name = plugin_path.rsplit('.', 1)
            module = __import__(module_path, fromlist=[class_name])
            plugin_class = getattr(module, class_name)

            if not issubclass(plugin_class, BasePlugin):
                raise ValueError(f"Plugin {plugin_path} must inherit from BasePlugin")

            plugin = plugin_class(config)

            if plugin.is_enabled():
                self._plugins[plugin.get_name()] = plugin
                logger.info(f"Loaded plugin: {plugin.get_name()} v{plugin.get_version()}")
            else:
                logger.info(f"Plugin {plugin.get_name()} is disabled")

        except Exception as e:
            logger.error(f"Error loading plugin {plugin_path}: {e}")
            raise

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """
        Get a plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None
        """
        return self._plugins.get(name)

    def get_plugins(self) -> List[BasePlugin]:
        """Get all loaded plugins."""
        return list(self._plugins.values())

    def get_enabled_plugins(self) -> List[BasePlugin]:
        """Get all enabled plugins."""
        return [plugin for plugin in self._plugins.values() if plugin.is_enabled()]

    def unload_plugin(self, name: str) -> bool:
        """
        Unload a plugin.

        Args:
            name: Plugin name

        Returns:
            True if plugin was unloaded, False if not found
        """
        if name in self._plugins:
            del self._plugins[name]
            logger.info(f"Unloaded plugin: {name}")
            return True
        return False

    def reload_plugins(self) -> None:
        """Reload all plugins."""
        self._plugins.clear()
        self._loaded = False
        self.load_plugins()

    def run_pre_registration_hooks(self, registry, schema_name: str, **kwargs) -> Dict[str, Any]:
        """
        Run pre-registration hooks for all enabled plugins.

        Args:
            registry: Schema registry instance
            schema_name: Schema name
            **kwargs: Registration parameters

        Returns:
            Modified registration parameters
        """
        self.load_plugins()
        modified_kwargs = kwargs.copy()

        for plugin in self.get_enabled_plugins():
            try:
                result = plugin.pre_registration_hook(registry, schema_name, **modified_kwargs)
                if isinstance(result, dict):
                    modified_kwargs.update(result)
            except Exception as e:
                logger.error(f"Error in pre-registration hook for plugin {plugin.get_name()}: {e}")

        return modified_kwargs

    def run_post_registration_hooks(self, registry, schema_info) -> None:
        """
        Run post-registration hooks for all enabled plugins.

        Args:
            registry: Schema registry instance
            schema_info: Schema information
        """
        self.load_plugins()

        for plugin in self.get_enabled_plugins():
            try:
                plugin.post_registration_hook(registry, schema_info)
            except Exception as e:
                logger.error(f"Error in post-registration hook for plugin {plugin.get_name()}: {e}")

    def run_discovery_hooks(self, registry) -> None:
        """
        Run discovery hooks for all enabled plugins.

        Args:
            registry: Schema registry instance
        """
        self.load_plugins()

        for plugin in self.get_enabled_plugins():
            try:
                plugin.discovery_hook(registry)
            except Exception as e:
                logger.error(f"Error in discovery hook for plugin {plugin.get_name()}: {e}")

    def validate_schema(self, schema_info) -> List[str]:
        """
        Validate schema using all enabled plugins.

        Args:
            schema_info: Schema information

        Returns:
            List of validation errors from all plugins
        """
        self.load_plugins()
        errors = []

        for plugin in self.get_enabled_plugins():
            try:
                plugin_errors = plugin.validate_schema(schema_info)
                if plugin_errors:
                    errors.extend([f"{plugin.get_name()}: {error}" for error in plugin_errors])
            except Exception as e:
                logger.error(f"Error in schema validation for plugin {plugin.get_name()}: {e}")
                errors.append(f"{plugin.get_name()}: Validation error - {e}")

        return errors


# Global plugin manager instance
plugin_manager = PluginManager()
