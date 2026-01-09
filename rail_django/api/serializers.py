"""
Serializers for GraphQL schema management REST API.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


class SchemaSerializer:
    """Serializer for schema data validation and serialization."""

    @staticmethod
    def validate_create_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate data for schema creation.

        Args:
            data: Raw input data

        Returns:
            Dict: Validated and cleaned data

        Raises:
            ValueError: If validation fails
        """
        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary")

        # Required fields
        if 'name' not in data or not data['name']:
            raise ValueError("Schema name is required")

        name = str(data['name']).strip()
        if not name:
            raise ValueError("Schema name cannot be empty")

        # Validate name format
        if not name.replace('_', '').replace('-', '').isalnum():
            raise ValueError(
                "Schema name must contain only alphanumeric characters, hyphens, and underscores")

        # Build validated data with defaults
        validated_data = {
            'name': name,
            'description': str(data.get('description', f'Schema: {name}')).strip(),
            'version': str(data.get('version', '1.0.0')).strip(),
            'apps': SchemaSerializer._validate_list_field(data.get('apps', []), 'apps'),
            'models': SchemaSerializer._validate_list_field(data.get('models', []), 'models'),
            'exclude_models': SchemaSerializer._validate_list_field(data.get('exclude_models', []), 'exclude_models'),
            'settings': SchemaSerializer._validate_settings(data.get('settings', {})),
            'auto_discover': bool(data.get('auto_discover', True)),
            'enabled': bool(data.get('enabled', True))
        }

        return validated_data

    @staticmethod
    def validate_update_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate data for schema update.

        Args:
            data: Raw input data

        Returns:
            Dict: Validated and cleaned data

        Raises:
            ValueError: If validation fails
        """
        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary")

        validated_data = {}

        # Optional fields for update
        if 'description' in data:
            validated_data['description'] = str(data['description']).strip()

        if 'version' in data:
            validated_data['version'] = str(data['version']).strip()

        if 'apps' in data:
            validated_data['apps'] = SchemaSerializer._validate_list_field(data['apps'], 'apps')

        if 'models' in data:
            validated_data['models'] = SchemaSerializer._validate_list_field(
                data['models'], 'models')

        if 'exclude_models' in data:
            validated_data['exclude_models'] = SchemaSerializer._validate_list_field(
                data['exclude_models'], 'exclude_models')

        if 'settings' in data:
            validated_data['settings'] = SchemaSerializer._validate_settings(data['settings'])

        if 'auto_discover' in data:
            validated_data['auto_discover'] = bool(data['auto_discover'])

        if 'enabled' in data:
            validated_data['enabled'] = bool(data['enabled'])

        return validated_data

    @staticmethod
    def _validate_list_field(value: Any, field_name: str) -> List[str]:
        """
        Validate list field.

        Args:
            value: Field value to validate
            field_name: Name of the field for error messages

        Returns:
            List[str]: Validated list

        Raises:
            ValueError: If validation fails
        """
        if not isinstance(value, list):
            raise ValueError(f"{field_name} must be a list")

        validated_list = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError(f"All items in {field_name} must be strings")

            item = item.strip()
            if not item:
                raise ValueError(f"Empty strings not allowed in {field_name}")

            validated_list.append(item)

        return validated_list

    @staticmethod
    def _validate_settings(value: Any) -> Dict[str, Any]:
        """
        Validate settings field.

        Args:
            value: Settings value to validate

        Returns:
            Dict[str, Any]: Validated settings

        Raises:
            ValueError: If validation fails
        """
        if not isinstance(value, dict):
            raise ValueError("Settings must be a dictionary")

        # Ensure all keys are strings
        validated_settings = {}
        for key, val in value.items():
            if not isinstance(key, str):
                raise ValueError("All setting keys must be strings")

            validated_settings[key] = val

        return validated_settings

    @staticmethod
    def serialize_schema_summary(schema_info) -> Dict[str, Any]:
        """
        Serialize schema info for summary view.

        Args:
            schema_info: SchemaInfo instance

        Returns:
            Dict: Serialized schema summary
        """
        return {
            'name': schema_info.name,
            'description': schema_info.description,
            'version': schema_info.version,
            'enabled': schema_info.enabled,
            'auto_discover': schema_info.auto_discover,
            'apps_count': len(schema_info.apps),
            'models_count': len(schema_info.models),
            'exclude_models_count': len(schema_info.exclude_models),
            'created_at': schema_info.created_at.isoformat() if hasattr(schema_info, 'created_at') else None,
            'updated_at': schema_info.updated_at.isoformat() if hasattr(schema_info, 'updated_at') else None
        }

    @staticmethod
    def serialize_schema_detailed(schema_info) -> Dict[str, Any]:
        """
        Serialize schema info for detailed view.

        Args:
            schema_info: SchemaInfo instance

        Returns:
            Dict: Serialized schema details
        """
        return {
            'name': schema_info.name,
            'description': schema_info.description,
            'version': schema_info.version,
            'enabled': schema_info.enabled,
            'auto_discover': schema_info.auto_discover,
            'apps': schema_info.apps,
            'models': schema_info.models,
            'exclude_models': schema_info.exclude_models,
            'settings': schema_info.settings,
            'builder': str(schema_info.builder) if schema_info.builder else None,
            'created_at': schema_info.created_at.isoformat() if hasattr(schema_info, 'created_at') else None,
            'updated_at': schema_info.updated_at.isoformat() if hasattr(schema_info, 'updated_at') else None
        }


class ManagementActionSerializer:
    """Serializer for management action validation."""

    VALID_ACTIONS = ['enable', 'disable', 'clear_all']

    @staticmethod
    def validate_action_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate management action data.

        Args:
            data: Raw input data

        Returns:
            Dict: Validated action data

        Raises:
            ValueError: If validation fails
        """
        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary")

        if 'action' not in data:
            raise ValueError("Action is required")

        action = str(data['action']).strip().lower()
        if action not in ManagementActionSerializer.VALID_ACTIONS:
            raise ValueError(
                f"Invalid action. Must be one of: {', '.join(ManagementActionSerializer.VALID_ACTIONS)}")

        validated_data = {'action': action}

        # Schema name required for enable/disable actions
        if action in ['enable', 'disable']:
            if 'schema_name' not in data or not data['schema_name']:
                raise ValueError(f"Schema name is required for '{action}' action")

            validated_data['schema_name'] = str(data['schema_name']).strip()

        return validated_data


class HealthSerializer:
    """Serializer for health check data."""

    @staticmethod
    def serialize_health_status(
        total_schemas: int,
        enabled_schemas: int,
        disabled_schemas: int,
        registry_initialized: bool,
        issues: List[str]
    ) -> Dict[str, Any]:
        """
        Serialize health status data.

        Args:
            total_schemas: Total number of schemas
            enabled_schemas: Number of enabled schemas
            disabled_schemas: Number of disabled schemas
            registry_initialized: Whether registry is initialized
            issues: List of health issues

        Returns:
            Dict: Serialized health status
        """
        # Determine overall status
        if not registry_initialized:
            status = 'critical'
        elif issues:
            status = 'warning'
        elif enabled_schemas == 0:
            status = 'warning'
        else:
            status = 'healthy'

        return {
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'total_schemas': total_schemas,
            'enabled_schemas': enabled_schemas,
            'disabled_schemas': disabled_schemas,
            'registry_initialized': registry_initialized,
            'issues': issues,
            'uptime_seconds': None,  # Could be implemented with app startup tracking
            'version': '1.0.0'  # Could be read from package version
        }


class MetricsSerializer:
    """Serializer for metrics data."""

    @staticmethod
    def serialize_metrics(schemas: List, plugin_manager=None) -> Dict[str, Any]:
        """
        Serialize metrics data.

        Args:
            schemas: List of schema info objects
            plugin_manager: Plugin manager instance

        Returns:
            Dict: Serialized metrics
        """
        total_schemas = len(schemas)
        enabled_schemas = sum(1 for s in schemas if s.enabled)
        disabled_schemas = total_schemas - enabled_schemas
        auto_discover_schemas = sum(1 for s in schemas if s.auto_discover)

        # Count models and excluded models
        all_models = set()
        all_excluded_models = set()
        for schema in schemas:
            all_models.update(schema.models)
            all_excluded_models.update(schema.exclude_models)

        # Group by app
        schemas_by_app = {}
        for schema in schemas:
            for app in schema.apps:
                schemas_by_app[app] = schemas_by_app.get(app, 0) + 1

        # Group by version
        schemas_by_version = {}
        for schema in schemas:
            version = schema.version
            schemas_by_version[version] = schemas_by_version.get(version, 0) + 1

        # Plugin metrics
        plugin_metrics = {
            'total_plugins': 0,
            'enabled_plugins': 0,
            'plugin_names': []
        }

        if plugin_manager:
            try:
                plugins = plugin_manager.get_loaded_plugins()
                plugin_metrics['total_plugins'] = len(plugins)
                plugin_metrics['enabled_plugins'] = len([p for p in plugins if p.is_enabled()])
                plugin_metrics['plugin_names'] = [p.name for p in plugins]
            except Exception:
                # Handle case where plugin manager is not available
                pass

        return {
            'timestamp': datetime.now().isoformat(),
            'total_schemas': total_schemas,
            'enabled_schemas': enabled_schemas,
            'disabled_schemas': disabled_schemas,
            'auto_discover_schemas': auto_discover_schemas,
            'total_models': len(all_models),
            'total_excluded_models': len(all_excluded_models),
            'schemas_by_app': schemas_by_app,
            'schemas_by_version': schemas_by_version,
            'plugin_metrics': plugin_metrics,
            'average_models_per_schema': len(all_models) / total_schemas if total_schemas > 0 else 0,
            'average_apps_per_schema': sum(len(s.apps) for s in schemas) / total_schemas if total_schemas > 0 else 0
        }


class DiscoverySerializer:
    """Serializer for discovery data."""

    @staticmethod
    def serialize_discovery_status(
        total_schemas: int,
        auto_discover_schemas: int,
        discovery_enabled: bool = True
    ) -> Dict[str, Any]:
        """
        Serialize discovery status data.

        Args:
            total_schemas: Total number of schemas
            auto_discover_schemas: Number of schemas with auto-discovery enabled
            discovery_enabled: Whether discovery is globally enabled

        Returns:
            Dict: Serialized discovery status
        """
        return {
            'discovery_enabled': discovery_enabled,
            'total_schemas': total_schemas,
            'auto_discover_schemas': auto_discover_schemas,
            'manual_schemas': total_schemas - auto_discover_schemas,
            'last_discovery': None,  # Could be implemented with discovery tracking
            'discovery_hooks_count': 0  # Could be read from registry
        }

    @staticmethod
    def serialize_discovery_result(discovered_count: int) -> Dict[str, Any]:
        """
        Serialize discovery result data.

        Args:
            discovered_count: Number of schemas discovered

        Returns:
            Dict: Serialized discovery result
        """
        return {
            'discovered_count': discovered_count,
            'timestamp': datetime.now().isoformat(),
            'message': f'Schema discovery completed. Found {discovered_count} new schemas.'
        }
