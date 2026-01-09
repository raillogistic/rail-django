"""REST API views for GraphQL schema management.

This module provides REST API endpoints for managing GraphQL schemas,
including registration, discovery, health checks, and monitoring."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..core.registry import schema_registry
from ..plugins.base import plugin_manager
from .serializers import (
    DiscoverySerializer,
    HealthSerializer,
    ManagementActionSerializer,
    MetricsSerializer,
    SchemaSerializer,
)

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class BaseAPIView(View):
    """Base class for API views with common functionality."""

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        """Handle CORS and common headers."""
        response = super().dispatch(request, *args, **kwargs)

        # Add CORS headers if enabled
        if getattr(settings, 'GRAPHQL_SCHEMA_API_CORS_ENABLED', True):
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'

        return response

    def options(self, request: HttpRequest, *args, **kwargs):
        """Handle preflight requests."""
        return JsonResponse({}, status=200)

    def json_response(self, data: Dict[str, Any], status: int = 200) -> JsonResponse:
        """Create a JSON response with consistent formatting."""
        response_data = {
            'timestamp': datetime.now().isoformat(),
            'status': 'success' if 200 <= status < 300 else 'error',
            'data': data
        }
        return JsonResponse(response_data, status=status)

    def error_response(self, message: str, status: int = 400, details: Optional[Dict] = None) -> JsonResponse:
        """Create an error response."""
        error_data = {
            'message': message,
            'details': details or {}
        }
        return self.json_response(error_data, status=status)

    def parse_json_body(self, request: HttpRequest) -> Optional[Dict[str, Any]]:
        """Parse JSON body from request."""
        try:
            if request.content_type == 'application/json' and request.body:
                return json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Error parsing JSON body: {e}")
        return None


class SchemaListAPIView(BaseAPIView):
    """API view for listing and creating schemas."""

    def get(self, request: HttpRequest) -> JsonResponse:
        """
        List all registered schemas.

        Query parameters:
        - enabled: Filter by enabled status (true/false)
        - app: Filter by app name
        - format: Response format (summary/detailed)
        """
        try:
            enabled_filter = request.GET.get('enabled')
            app_filter = request.GET.get('app')
            format_type = request.GET.get('format', 'summary')

            schemas = schema_registry.list_schemas()

            # Apply filters
            if enabled_filter is not None:
                enabled_bool = enabled_filter.lower() == 'true'
                schemas = [s for s in schemas if s.enabled == enabled_bool]

            if app_filter:
                schemas = [s for s in schemas if app_filter in s.apps]

            # Format response
            if format_type == 'detailed':
                schema_data = [
                    {
                        'name': schema.name,
                        'description': schema.description,
                        'version': schema.version,
                        'apps': schema.apps,
                        'models': schema.models,
                        'exclude_models': schema.exclude_models,
                        'enabled': schema.enabled,
                        'auto_discover': schema.auto_discover,
                        'settings': schema.settings,
                        'created_at': getattr(schema, 'created_at', None),
                        'updated_at': getattr(schema, 'updated_at', None)
                    }
                    for schema in schemas
                ]
            else:
                schema_data = [
                    {
                        'name': schema.name,
                        'description': schema.description,
                        'version': schema.version,
                        'enabled': schema.enabled,
                        'apps_count': len(schema.apps),
                        'models_count': len(schema.models)
                    }
                    for schema in schemas
                ]

            return self.json_response({
                'schemas': schema_data,
                'total_count': len(schema_data),
                'enabled_count': len([s for s in schemas if s.enabled]),
                'disabled_count': len([s for s in schemas if not s.enabled])
            })

        except Exception as e:
            logger.error(f"Error listing schemas: {e}")
            return self.error_response(f"Failed to list schemas: {str(e)}", status=500)

    def post(self, request: HttpRequest) -> JsonResponse:
        """Create a new schema."""
        try:
            data = json.loads(request.body)

            # Validate input data
            validated_data = SchemaSerializer.validate_create_data(data)

            # Register schema
            schema_info = schema_registry.register_schema(**validated_data)

            return self.json_response({
                'message': f'Schema \'{validated_data["name"]}\' registered successfully',
                'schema': SchemaSerializer.serialize_schema_detailed(schema_info)
            }, status=201)

        except json.JSONDecodeError:
            return self.error_response('Invalid JSON body', status=400)
        except ValueError as e:
            return self.error_response(str(e), status=400)
        except Exception as e:
            logger.exception(f'Failed to create schema: {e}')
            return self.error_response('Failed to create schema', status=500)


class SchemaDetailAPIView(BaseAPIView):
    """API view for individual schema operations."""

    def get(self, request: HttpRequest, schema_name: str) -> JsonResponse:
        """Get detailed information about a specific schema."""
        try:
            schema_info = schema_registry.get_schema(schema_name)
            if not schema_info:
                return self.error_response(f"Schema '{schema_name}' not found", status=404)

            # Get schema builder info if available
            builder_info = None
            try:
                builder = schema_registry.get_schema_builder(schema_name)
                if builder:
                    builder_info = {
                        'has_builder': True,
                        'builder_type': type(builder).__name__
                    }
            except Exception:
                builder_info = {'has_builder': False}

            schema_data = {
                'name': schema_info.name,
                'description': schema_info.description,
                'version': schema_info.version,
                'apps': schema_info.apps,
                'models': schema_info.models,
                'exclude_models': schema_info.exclude_models,
                'enabled': schema_info.enabled,
                'auto_discover': schema_info.auto_discover,
                'settings': schema_info.settings,
                'builder': builder_info,
                'created_at': getattr(schema_info, 'created_at', None),
                'updated_at': getattr(schema_info, 'updated_at', None)
            }

            return self.json_response({'schema': schema_data})

        except Exception as e:
            logger.error(f"Error getting schema '{schema_name}': {e}")
            return self.error_response(f"Failed to get schema: {str(e)}", status=500)

    def put(self, request: HttpRequest, schema_name: str) -> JsonResponse:
        """Update a schema configuration."""
        try:
            # Check if schema exists
            if not schema_registry.schema_exists(schema_name):
                return self.error_response(f"Schema '{schema_name}' not found", status=404)

            data = self.parse_json_body(request)
            if not data:
                return self.error_response("Invalid JSON body", status=400)

            # Get current schema info
            current_schema = schema_registry.get_schema(schema_name)

            # Update schema with new data
            schema_info = schema_registry.register_schema(
                name=schema_name,
                description=data.get('description', current_schema.description),
                version=data.get('version', current_schema.version),
                apps=data.get('apps', current_schema.apps),
                models=data.get('models', current_schema.models),
                exclude_models=data.get('exclude_models', current_schema.exclude_models),
                settings=data.get('settings', current_schema.settings),
                auto_discover=data.get('auto_discover', current_schema.auto_discover),
                enabled=data.get('enabled', current_schema.enabled)
            )

            return self.json_response({
                'message': f"Schema '{schema_name}' updated successfully",
                'schema': {
                    'name': schema_info.name,
                    'description': schema_info.description,
                    'version': schema_info.version,
                    'enabled': schema_info.enabled
                }
            })

        except Exception as e:
            logger.error(f"Error updating schema '{schema_name}': {e}")
            return self.error_response(f"Failed to update schema: {str(e)}", status=500)

    def delete(self, request: HttpRequest, schema_name: str) -> JsonResponse:
        """Delete a schema registration."""
        try:
            success = schema_registry.unregister_schema(schema_name)
            if not success:
                return self.error_response(f"Schema '{schema_name}' not found", status=404)

            return self.json_response({
                'message': f"Schema '{schema_name}' deleted successfully"
            })

        except Exception as e:
            logger.error(f"Error deleting schema '{schema_name}': {e}")
            return self.error_response(f"Failed to delete schema: {str(e)}", status=500)


class SchemaManagementAPIView(BaseAPIView):
    """API view for schema management operations."""

    def post(self, request: HttpRequest) -> JsonResponse:
        """Execute management actions."""
        try:
            data = json.loads(request.body)

            # Validate action data
            validated_data = ManagementActionSerializer.validate_action_data(data)
            action = validated_data['action']

            if action == 'enable':
                schema_name = validated_data['schema_name']
                schema_registry.enable_schema(schema_name)
                return self.json_response({
                    'message': f'Schema \'{schema_name}\' enabled successfully'
                })

            elif action == 'disable':
                schema_name = validated_data['schema_name']
                schema_registry.disable_schema(schema_name)
                return self.json_response({
                    'message': f'Schema \'{schema_name}\' disabled successfully'
                })

            elif action == 'clear_all':
                schema_registry.clear()
                return self.json_response({
                    'message': 'All schemas cleared successfully'
                })

            else:
                return self.error_response(f'Unknown action: {action}', status=400)

        except json.JSONDecodeError:
            return self.error_response('Invalid JSON body', status=400)
        except ValueError as e:
            return self.error_response(str(e), status=400)
        except Exception as e:
            logger.exception(f'Failed to execute management action: {e}')
            return self.error_response('Failed to execute action', status=500)


class SchemaDiscoveryAPIView(BaseAPIView):
    """API view for schema discovery operations."""

    def post(self, request: HttpRequest) -> JsonResponse:
        """Trigger schema auto-discovery."""
        try:
            discovered_count = schema_registry.auto_discover_schemas()

            result_data = DiscoverySerializer.serialize_discovery_result(discovered_count)

            return self.json_response(result_data)

        except Exception as e:
            logger.exception(f"Error in schema discovery: {e}")
            return self.error_response(f"Discovery failed: {str(e)}", status=500)

    def get(self, request: HttpRequest) -> JsonResponse:
        """Get discovery status and configuration."""
        try:
            schemas = schema_registry.list_schemas()
            auto_discover_count = sum(1 for s in schemas if s.auto_discover)

            discovery_data = DiscoverySerializer.serialize_discovery_status(
                total_schemas=len(schemas),
                auto_discover_schemas=auto_discover_count
            )

            return self.json_response(discovery_data)

        except Exception as e:
            logger.exception(f"Error getting discovery status: {e}")
            return self.error_response(f"Failed to get discovery status: {str(e)}", status=500)


class SchemaHealthAPIView(BaseAPIView):
    """API view for schema health checks."""

    def get(self, request: HttpRequest) -> JsonResponse:
        """Get overall schema registry health status."""
        try:
            schemas = schema_registry.list_schemas()
            enabled_schemas = [s for s in schemas if s.enabled]

            # Basic health metrics
            health_data = {
                'status': 'healthy',
                'total_schemas': len(schemas),
                'enabled_schemas': len(enabled_schemas),
                'disabled_schemas': len(schemas) - len(enabled_schemas),
                'registry_initialized': True,
                'plugin_count': len(plugin_manager.get_enabled_plugins()),
                'timestamp': datetime.now().isoformat()
            }

            # Check for potential issues
            issues = []
            if len(enabled_schemas) == 0:
                issues.append('No enabled schemas found')
                health_data['status'] = 'warning'

            if len(schemas) > 50:  # Arbitrary threshold
                issues.append('Large number of schemas may impact performance')
                health_data['status'] = 'warning'

            health_data['issues'] = issues

            return self.json_response(health_data)

        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return self.json_response({
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }, status=500)


class SchemaMetricsAPIView(BaseAPIView):
    """API view for schema metrics and statistics."""

    def get(self, request: HttpRequest) -> JsonResponse:
        """Get detailed metrics about schema registry."""
        try:
            schemas = schema_registry.list_schemas()

            metrics_data = MetricsSerializer.serialize_metrics(
                schemas=schemas,
                plugin_manager=plugin_manager
            )

            return self.json_response({
                'metrics': metrics_data
            })

        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            return self.error_response(f"Failed to get metrics: {str(e)}", status=500)
