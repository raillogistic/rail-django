"""
SchemaDetailAPIView implementation.
"""

import logging
from django.http import HttpRequest, JsonResponse
from .base import BaseAPIView
from ...core.registry import schema_registry

logger = logging.getLogger(__name__)


class SchemaDetailAPIView(BaseAPIView):
    """API view for individual schema operations."""

    auth_required = True
    rate_limit_enabled = True

    def get(self, request: HttpRequest, schema_name: str) -> JsonResponse:
        """Get detailed information about a specific schema."""
        try:
            schema_info = schema_registry.get_schema(schema_name)
            if not schema_info: return self.error_response(f"Schema '{schema_name}' not found", status=404)
            builder = schema_registry.get_cached_schema_builder(schema_name)
            builder_info = {'has_builder': True, 'builder_type': type(builder).__name__} if builder else {'has_builder': False}
            schema_data = {'name': schema_info.name, 'description': schema_info.description, 'version': schema_info.version, 'apps': schema_info.apps, 'models': schema_info.models, 'exclude_models': schema_info.exclude_models, 'enabled': schema_info.enabled, 'auto_discover': schema_info.auto_discover, 'settings': schema_info.settings, 'builder': builder_info, 'created_at': getattr(schema_info, 'created_at', None), 'updated_at': getattr(schema_info, 'updated_at', None)}
            return self.json_response({'schema': schema_data})
        except Exception as e:
            logger.error(f"Error getting schema '{schema_name}': {e}")
            return self.error_response(f"Failed to get schema: {str(e)}", status=500)

    def put(self, request: HttpRequest, schema_name: str) -> JsonResponse:
        """Update a schema configuration."""
        admin_check = self._require_admin(request)
        if admin_check: return admin_check
        try:
            if not schema_registry.schema_exists(schema_name): return self.error_response(f"Schema '{schema_name}' not found", status=404)
            data = self.parse_json_body(request)
            if not data: return self.error_response("Invalid JSON body", status=400)
            current_schema = schema_registry.get_schema(schema_name)
            schema_info = schema_registry.register_schema(name=schema_name, description=data.get('description', current_schema.description), version=data.get('version', current_schema.version), apps=data.get('apps', current_schema.apps), models=data.get('models', current_schema.models), exclude_models=data.get('exclude_models', current_schema.exclude_models), settings=data.get('settings', current_schema.settings), auto_discover=data.get('auto_discover', current_schema.auto_discover), enabled=data.get('enabled', current_schema.enabled))
            return self.json_response({'message': f"Schema '{schema_name}' updated successfully", 'schema': {'name': schema_info.name, 'description': schema_info.description, 'version': schema_info.version, 'enabled': schema_info.enabled}})
        except Exception as e:
            logger.error(f"Error updating schema '{schema_name}': {e}")
            return self.error_response(f"Failed to update schema: {str(e)}", status=500)

    def delete(self, request: HttpRequest, schema_name: str) -> JsonResponse:
        """Delete a schema registration."""
        admin_check = self._require_admin(request)
        if admin_check: return admin_check
        try:
            if not schema_registry.unregister_schema(schema_name): return self.error_response(f"Schema '{schema_name}' not found", status=404)
            return self.json_response({'message': f"Schema '{schema_name}' deleted successfully"})
        except Exception as e:
            logger.error(f"Error deleting schema '{schema_name}': {e}")
            return self.error_response(f"Failed to delete schema: {str(e)}", status=500)
