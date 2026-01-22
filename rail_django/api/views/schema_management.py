"""
Schema management and discovery views.
"""

import logging
from datetime import datetime
from django.http import HttpRequest, JsonResponse
from .base import BaseAPIView
from ...core.registry import schema_registry
from ...plugins.base import plugin_manager
from ..serializers import ManagementActionSerializer, DiscoverySerializer, MetricsSerializer

logger = logging.getLogger(__name__)


class SchemaManagementAPIView(BaseAPIView):
    """API view for schema management operations."""
    auth_required = True
    rate_limit_enabled = True

    def post(self, request: HttpRequest) -> JsonResponse:
        admin_check = self._require_admin(request)
        if admin_check: return admin_check
        try:
            data = self.parse_json_body(request)
            if data is None: return self.error_response('Invalid JSON body', status=400)
            validated_data = ManagementActionSerializer.validate_action_data(data)
            action = validated_data['action']
            if action == 'enable':
                schema_registry.enable_schema(validated_data['schema_name'])
                return self.json_response({'message': f"Schema '{validated_data['schema_name']}' enabled successfully"})
            elif action == 'disable':
                schema_registry.disable_schema(validated_data['schema_name'])
                return self.json_response({'message': f"Schema '{validated_data['schema_name']}' disabled successfully"})
            elif action == 'clear_all':
                schema_registry.clear()
                return self.json_response({'message': 'All schemas cleared successfully'})
            return self.error_response(f'Unknown action: {action}', status=400)
        except ValueError as e:
            return self.error_response(str(e), status=400)
        except Exception as e:
            logger.exception(f'Failed to execute management action: {e}')
            return self.error_response('Failed to execute action', status=500)


class SchemaDiscoveryAPIView(BaseAPIView):
    """API view for schema discovery operations."""
    auth_required = True
    rate_limit_enabled = True

    def post(self, request: HttpRequest) -> JsonResponse:
        admin_check = self._require_admin(request)
        if admin_check: return admin_check
        try:
            count = schema_registry.auto_discover_schemas()
            return self.json_response(DiscoverySerializer.serialize_discovery_result(count))
        except Exception as e:
            logger.exception(f"Error in schema discovery: {e}")
            return self.error_response(f"Discovery failed: {str(e)}", status=500)

    def get(self, request: HttpRequest) -> JsonResponse:
        try:
            schemas = schema_registry.list_schemas()
            return self.json_response(DiscoverySerializer.serialize_discovery_status(len(schemas), sum(1 for s in schemas if s.auto_discover)))
        except Exception as e:
            logger.exception(f"Error getting discovery status: {e}")
            return self.error_response(f"Failed to get discovery status: {str(e)}", status=500)


class SchemaHealthAPIView(BaseAPIView):
    """API view for schema health checks."""
    def get(self, request: HttpRequest) -> JsonResponse:
        try:
            schemas = schema_registry.list_schemas()
            enabled = [s for s in schemas if s.enabled]
            health_data = {'status': 'healthy', 'total_schemas': len(schemas), 'enabled_schemas': len(enabled), 'disabled_schemas': len(schemas) - len(enabled), 'registry_initialized': True, 'plugin_count': len(plugin_manager.get_enabled_plugins()), 'timestamp': datetime.now().isoformat()}
            issues = []
            if len(enabled) == 0: health_data['status'] = 'warning'; issues.append('No enabled schemas found')
            if len(schemas) > 50: health_data['status'] = 'warning'; issues.append('Large number of schemas may impact performance')
            health_data['issues'] = issues
            return self.json_response(health_data)
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return self.json_response({'status': 'unhealthy', 'error': str(e), 'timestamp': datetime.now().isoformat()}, status=500)


class SchemaMetricsAPIView(BaseAPIView):
    """API view for schema metrics and statistics."""
    auth_required = True
    rate_limit_enabled = True

    def get(self, request: HttpRequest) -> JsonResponse:
        admin_check = self._require_admin(request)
        if admin_check: return admin_check
        try:
            return self.json_response({'metrics': MetricsSerializer.serialize_metrics(schema_registry.list_schemas(), plugin_manager)})
        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            return self.error_response(f"Failed to get metrics: {str(e)}", status=500)
