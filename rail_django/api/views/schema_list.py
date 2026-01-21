"SchemaListAPIView implementation."

import logging
from django.http import HttpRequest, JsonResponse
from .base import BaseAPIView
from ...core.registry import schema_registry
from ..serializers import SchemaSerializer

logger = logging.getLogger(__name__)


class SchemaListAPIView(BaseAPIView):
    """API view for listing and creating schemas."""

    auth_required = True
    rate_limit_enabled = True

    def get(self, request: HttpRequest) -> JsonResponse:
        """List all registered schemas."""
        try:
            enabled_filter, app_filter, format_type = request.GET.get('enabled'), request.GET.get('app'), request.GET.get('format', 'summary')
            schemas = schema_registry.list_schemas()
            if enabled_filter is not None:
                enabled_bool = enabled_filter.lower() == 'true'
                schemas = [s for s in schemas if s.enabled == enabled_bool]
            if app_filter:
                schemas = [s for s in schemas if app_filter in s.apps]

            if format_type == 'detailed':
                schema_data = [{'name': s.name, 'description': s.description, 'version': s.version, 'apps': s.apps, 'models': s.models, 'exclude_models': s.exclude_models, 'enabled': s.enabled, 'auto_discover': s.auto_discover, 'settings': s.settings, 'created_at': getattr(s, 'created_at', None), 'updated_at': getattr(s, 'updated_at', None)} for s in schemas]
            else:
                schema_data = [{'name': s.name, 'description': s.description, 'version': s.version, 'enabled': s.enabled, 'apps_count': len(s.apps), 'models_count': len(s.models)} for s in schemas]

            return self.json_response({'schemas': schema_data, 'total_count': len(schema_data), 'enabled_count': len([s for s in schemas if s.enabled]), 'disabled_count': len([s for s in schemas if not s.enabled])})
        except Exception as e:
            logger.error(f"Error listing schemas: {e}")
            return self.error_response(f"Failed to list schemas: {str(e)}", status=500)

    def post(self, request: HttpRequest) -> JsonResponse:
        """Create a new schema."""
        admin_check = self._require_admin(request)
        if admin_check: return admin_check
        try:
            data = self.parse_json_body(request)
            if data is None: return self.error_response('Invalid JSON body', status=400)
            validated_data = SchemaSerializer.validate_create_data(data)
            schema_info = schema_registry.register_schema(**validated_data)
            return self.json_response({'message': f'Schema \'{validated_data["name"]}\' registered successfully', 'schema': SchemaSerializer.serialize_schema_detailed(schema_info)}, status=201)
        except ValueError as e: return self.error_response(str(e), status=400)
        except Exception as e:
            logger.exception(f'Failed to create schema: {e}')
            return self.error_response('Failed to create schema', status=500)
