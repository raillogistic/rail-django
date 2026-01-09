"""
Django app configuration for rail-django library.

This module configures:
- Django application for automatic GraphQL schema generation
- Signal and hook configuration
- Core component initialization
- Library settings validation
"""

import logging

from django.apps import AppConfig as BaseAppConfig

logger = logging.getLogger(__name__)


class AppConfig(BaseAppConfig):
    """Django app configuration for rail-django library."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "rail_django"
    verbose_name = "Rail Django GraphQL"
    label = "rail_django"

    def ready(self):
        """Initialize the application after Django has loaded."""
        logger.info("AppConfig.ready() method called - starting initialization")
        try:
            # Setup performance monitoring if enabled
            self._setup_performance_monitoring()

            # Setup Django signals
            self._setup_signals()

            # Validate library configuration
            self._validate_configuration()

            # Initialize schema registry
            self._initialize_schema_registry()

            # Optionally prebuild schemas on startup
            self._prebuild_schemas_on_startup()

            # Invalidate metadata cache on startup
            self._invalidate_cache_on_startup()

            logger.info("Rail Django GraphQL library initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing Rail Django GraphQL library: {e}")
            # Don't raise in production to avoid breaking the app
            if self._is_debug_mode():
                raise

    def _setup_performance_monitoring(self):
        """Setup performance monitoring if enabled."""
        try:
            # Use hierarchical settings proxy and new lowercase keys
            from .config_proxy import get_settings_proxy

            settings = get_settings_proxy()

            if settings.get("monitoring_settings.enable_metrics", False):
                from .middleware.performance import setup_performance_monitoring

                setup_performance_monitoring()
                logger.debug("Performance monitoring setup completed")
        except ImportError as e:
            logger.warning(f"Could not setup performance monitoring: {e}")
        except Exception as e:
            logger.error(f"Error setting up performance monitoring: {e}")

    def _setup_signals(self):
        """Configure Django signals for automatic schema generation."""
        try:
            # Use hierarchical settings proxy and new lowercase keys
            from .config_proxy import get_settings_proxy

            settings = get_settings_proxy()

            if settings.get("schema_registry.enable_registry", False):
                # Import signals to register them
                from . import signals  # This will be created later

                logger.debug("Django signals setup completed")
        except ImportError as e:
            logger.debug(f"Signals module not found, skipping: {e}")
        except Exception as e:
            logger.warning(f"Could not setup signals: {e}")

    def _validate_configuration(self):
        """Validate library configuration."""
        try:
            from .core.config_loader import ConfigLoader

            ConfigLoader.validate_configuration()
            logger.debug("Configuration validation completed")
        except Exception as e:
            logger.warning(f"Configuration validation failed: {e}")
            if self._is_debug_mode():
                raise

    def _initialize_schema_registry(self):
        """Initialize the schema registry."""
        try:
            # Use hierarchical settings proxy and new lowercase keys
            from .config_proxy import get_settings_proxy

            settings = get_settings_proxy()

            if settings.get("schema_registry.enable_registry", False):
                from .core.registry import schema_registry

                schema_registry.discover_schemas()
                logger.debug("Schema registry initialization completed")
        except ImportError as e:
            logger.debug(f"Schema registry not available: {e}")
        except Exception as e:
            logger.warning(f"Could not initialize schema registry: {e}")

    def _prebuild_schemas_on_startup(self):
        """Prebuild GraphQL schemas on server startup if enabled in settings."""
        try:
            from .core.schema import get_schema_builder
            from .core.settings import SchemaSettings

            schema_settings = SchemaSettings.from_schema("default")
            if schema_settings.prebuild_on_startup:
                builder = get_schema_builder("default")
                # Build the schema once at startup
                builder.get_schema()
                logger.info("Prebuilt GraphQL schema 'default' on startup")
        except ImportError as e:
            logger.debug(f"Could not prebuild schema on startup: {e}")
        except Exception as e:
            logger.warning(f"Error during schema prebuild on startup: {e}")

    def _is_debug_mode(self):
        """Check if we're in debug mode."""
        try:
            from django.conf import settings as django_settings

            return getattr(django_settings, "DEBUG", False)
        except:
            return False

    def _configure_environment(self):
        """Configure l'environnement pour l'application."""
        import os

        # Configuration des logs pour l'application
        logging.getLogger("rail_django").setLevel(
            logging.DEBUG if os.environ.get("DEBUG") else logging.INFO
        )

    def _invalidate_cache_on_startup(self):
        """Invalidate metadata cache on application startup."""
        try:
            from .extensions.metadata import invalidate_cache_on_startup

            invalidate_cache_on_startup()
            logger.info("Metadata cache invalidated on startup")
        except ImportError:
            logger.warning("Could not import cache invalidation function")
        except Exception as e:
            logger.error(f"Error invalidating cache on startup: {e}")


# Backward compatibility alias
DjangoGraphQLAutoConfig = AppConfig
