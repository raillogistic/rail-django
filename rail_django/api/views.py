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

from ..core.services import get_rate_limiter
from ..config_proxy import get_setting

from ..core.registry import schema_registry
from ..plugins.base import plugin_manager
from ..core.schema_snapshots import (
    get_schema_diff,
    get_schema_snapshot,
    list_schema_snapshots,
)
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

    auth_required = False
    rate_limit_enabled = False
    _json_body_cache_attr = "_rail_json_body_cache"
    _json_body_cache_set_attr = "_rail_json_body_cache_set"

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        """Handle CORS and common headers."""
        auth_required = self.auth_required and getattr(
            settings, "GRAPHQL_SCHEMA_API_AUTH_REQUIRED", True
        )
        if auth_required:
            auth_response = self._authenticate_request(request)
            if auth_response is not None:
                self._audit_request(
                    request,
                    auth_response,
                    path_params=kwargs,
                    extra_data={"auth_failed": True},
                )
                return auth_response

        if self.rate_limit_enabled and request.method != "OPTIONS":
            rate_limit_response = self._check_rate_limit(request)
            if rate_limit_response is not None:
                self._audit_request(
                    request,
                    rate_limit_response,
                    path_params=kwargs,
                    extra_data={"rate_limited": True},
                )
                return rate_limit_response

        response = super().dispatch(request, *args, **kwargs)

        # Add CORS headers if enabled
        if getattr(settings, "GRAPHQL_SCHEMA_API_CORS_ENABLED", True):
            allow_all = bool(getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False))
            if allow_all and not getattr(settings, "DEBUG", False):
                allow_all = False

            allowed_origins = getattr(
                settings, "GRAPHQL_SCHEMA_API_CORS_ALLOWED_ORIGINS", None
            )
            if allowed_origins is None:
                allowed_origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])

            origin = request.META.get("HTTP_ORIGIN")
            if allow_all:
                response["Access-Control-Allow-Origin"] = "*"
            elif origin and origin in allowed_origins:
                response["Access-Control-Allow-Origin"] = origin
                response["Vary"] = "Origin"
            elif not allowed_origins:
                response["Access-Control-Allow-Origin"] = "*"

            response["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"

        self._audit_request(request, response, path_params=kwargs)
        return response

    def _check_rate_limit(self, request: HttpRequest) -> Optional[JsonResponse]:
        """Apply a basic rate limit using the shared limiter."""
        limiter = get_rate_limiter()
        result = limiter.check("schema_api", request=request)
        if not result.allowed:
            return self.error_response(
                "Rate limit exceeded",
                status=429,
                details={"retry_after": result.retry_after},
            )
        return None

    def _authenticate_request(self, request: HttpRequest) -> Optional[JsonResponse]:
        """Authenticate request using JWT access tokens."""
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header:
            return self.error_response("Authentication required", status=401)

        if not (auth_header.startswith("Bearer ") or auth_header.startswith("Token ")):
            return self.error_response("Invalid authorization header", status=401)

        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or not parts[1]:
            return self.error_response("Invalid token format", status=401)

        token = parts[1]
        try:
            from ..extensions.auth import JWTManager
            from django.contrib.auth import get_user_model

            payload = JWTManager.verify_token(token, expected_type="access")
            if not payload:
                return self.error_response("Invalid or expired token", status=401)

            user_id = payload.get("user_id") or payload.get("sub")
            if not user_id:
                return self.error_response("Invalid token payload", status=401)

            User = get_user_model()
            user = User.objects.filter(id=user_id, is_active=True).first()
            if not user:
                return self.error_response("User not found or inactive", status=401)

            request.user = user
            request.jwt_payload = payload
            return None
        except Exception as exc:
            logger.warning("API authentication failed: %s", exc)
            return self.error_response("Authentication failed", status=401)

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
        if getattr(request, self._json_body_cache_set_attr, False):
            return getattr(request, self._json_body_cache_attr, None)

        parsed_body = None
        try:
            content_type = (request.content_type or "").lower()
            if request.body and (not content_type or content_type.startswith("application/json")):
                parsed_body = json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Error parsing JSON body: {e}")
        setattr(request, self._json_body_cache_attr, parsed_body)
        setattr(request, self._json_body_cache_set_attr, True)
        return parsed_body

    def _audit_request(
        self,
        request: HttpRequest,
        response: JsonResponse,
        *,
        path_params: Optional[Dict[str, Any]] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        if request.method == "OPTIONS":
            return

        try:
            from ..extensions.audit import AuditEventType, log_audit_event
        except Exception:
            return

        body_data = None
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            body_data = self.parse_json_body(request)

        event_type = self._get_audit_event_type(request, body_data, AuditEventType)

        additional_data: Dict[str, Any] = {
            "component": "schema_api",
            "view": self.__class__.__name__,
            "status_code": response.status_code,
        }
        if path_params:
            additional_data["path_params"] = path_params
        if isinstance(body_data, dict) and body_data.get("action"):
            additional_data["action"] = body_data.get("action")
        if extra_data:
            additional_data.update(extra_data)

        success = response.status_code < 400
        error_message = None
        if not success:
            error_message = self._extract_error_message(response)

        log_audit_event(
            request,
            event_type,
            success=success,
            error_message=error_message,
            additional_data=additional_data,
        )

    def _get_audit_event_type(
        self,
        request: HttpRequest,
        body_data: Optional[Dict[str, Any]],
        audit_enum: Any,
    ) -> Any:
        method = request.method.upper()
        view_name = self.__class__.__name__

        if method in {"GET", "HEAD", "OPTIONS"}:
            return audit_enum.DATA_ACCESS
        if method in {"PUT", "PATCH"}:
            return audit_enum.UPDATE
        if method == "DELETE":
            return audit_enum.DELETE
        if method == "POST":
            if view_name in {"SchemaManagementAPIView", "SchemaDiscoveryAPIView"}:
                action = body_data.get("action") if isinstance(body_data, dict) else None
                if action == "clear_all":
                    return audit_enum.DELETE
                return audit_enum.UPDATE
            return audit_enum.CREATE
        return audit_enum.DATA_ACCESS

    def _extract_error_message(self, response: JsonResponse) -> Optional[str]:
        try:
            payload = json.loads(response.content.decode("utf-8"))
        except Exception:
            return None

        if isinstance(payload, dict):
            data = payload.get("data", payload)
            if isinstance(data, dict):
                return data.get("message") or data.get("error")
            return payload.get("message") or payload.get("error")
        return None

    def _require_admin(self, request: HttpRequest) -> Optional[JsonResponse]:
        """Ensure the request is authenticated and authorized for management actions."""
        if not getattr(settings, "GRAPHQL_SCHEMA_API_AUTH_REQUIRED", True):
            return None
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return self.error_response("Authentication required", status=401)

        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return None

        required_perms = getattr(
            settings,
            "GRAPHQL_SCHEMA_API_REQUIRED_PERMISSIONS",
            ["rail_django.manage_schema"],
        )
        if required_perms and not any(user.has_perm(perm) for perm in required_perms):
            return self.error_response("Admin permissions required", status=403)

        return None


class SchemaListAPIView(BaseAPIView):
    """API view for listing and creating schemas."""

    auth_required = True
    rate_limit_enabled = True

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
        admin_check = self._require_admin(request)
        if admin_check:
            return admin_check

        try:
            data = self.parse_json_body(request)
            if data is None:
                return self.error_response('Invalid JSON body', status=400)

            # Validate input data
            validated_data = SchemaSerializer.validate_create_data(data)

            # Register schema
            schema_info = schema_registry.register_schema(**validated_data)

            return self.json_response({
                'message': f'Schema \'{validated_data["name"]}\' registered successfully',
                'schema': SchemaSerializer.serialize_schema_detailed(schema_info)
            }, status=201)

        except ValueError as e:
            return self.error_response(str(e), status=400)
        except Exception as e:
            logger.exception(f'Failed to create schema: {e}')
            return self.error_response('Failed to create schema', status=500)


class SchemaDetailAPIView(BaseAPIView):
    """API view for individual schema operations."""

    auth_required = True
    rate_limit_enabled = True

    def get(self, request: HttpRequest, schema_name: str) -> JsonResponse:
        """Get detailed information about a specific schema."""
        try:
            schema_info = schema_registry.get_schema(schema_name)
            if not schema_info:
                return self.error_response(f"Schema '{schema_name}' not found", status=404)

            # Get schema builder info if available without instantiating
            builder = schema_registry.get_cached_schema_builder(schema_name)
            if builder:
                builder_info = {
                    'has_builder': True,
                    'builder_type': type(builder).__name__
                }
            else:
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
        admin_check = self._require_admin(request)
        if admin_check:
            return admin_check

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
        admin_check = self._require_admin(request)
        if admin_check:
            return admin_check

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

    auth_required = True
    rate_limit_enabled = True

    def post(self, request: HttpRequest) -> JsonResponse:
        """Execute management actions."""
        admin_check = self._require_admin(request)
        if admin_check:
            return admin_check

        try:
            data = self.parse_json_body(request)
            if data is None:
                return self.error_response('Invalid JSON body', status=400)

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
        """Trigger schema auto-discovery."""
        admin_check = self._require_admin(request)
        if admin_check:
            return admin_check

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

    auth_required = True
    rate_limit_enabled = True

    def get(self, request: HttpRequest) -> JsonResponse:
        """Get detailed metrics about schema registry."""
        admin_check = self._require_admin(request)
        if admin_check:
            return admin_check

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


class SchemaExportAPIView(BaseAPIView):
    """API view for exporting schema snapshots or current schema."""

    auth_required = True
    rate_limit_enabled = True

    def get(self, request: HttpRequest, schema_name: str) -> JsonResponse:
        admin_check = self._require_admin(request)
        if admin_check:
            return admin_check

        if not get_setting("schema_registry.enable_schema_export", True, schema_name):
            return self.error_response("Schema export disabled", status=403)

        schema_info = schema_registry.get_schema(schema_name)
        if not schema_info:
            return self.error_response(f"Schema '{schema_name}' not found", status=404)

        export_format = str(request.GET.get("format", "json")).lower()
        version = request.GET.get("version") or request.GET.get("schema_version")

        snapshot = get_schema_snapshot(schema_name, version=str(version)) if version else None
        if version and snapshot is None:
            return self.error_response("Schema snapshot not found", status=404)
        if snapshot:
            schema_json = snapshot.schema_json
            schema_sdl = snapshot.schema_sdl or ""
            schema_hash = snapshot.schema_hash
        else:
            try:
                builder = schema_registry.get_schema_builder(schema_name)
                schema = builder.get_schema()
            except Exception as exc:
                return self.error_response(f"Schema build failed: {exc}", status=500)

            try:
                from ..introspection.schema_introspector import SchemaIntrospector
                from graphql.utilities import print_schema
                import hashlib

                graphql_schema = getattr(schema, "graphql_schema", None)
                if graphql_schema is None:
                    return self.error_response("Schema is not ready", status=500)

                introspector = SchemaIntrospector()
                introspection = introspector.introspect_schema(
                    graphql_schema,
                    schema_name,
                    version=str(builder.get_schema_version()),
                    description=schema_info.description,
                )
                schema_json = introspection.to_dict()
                schema_sdl = print_schema(graphql_schema)
                schema_hash = hashlib.sha256(schema_sdl.encode("utf-8")).hexdigest()
            except Exception as exc:
                return self.error_response(f"Schema export failed: {exc}", status=500)

        if export_format == "sdl":
            return self.json_response(
                {
                    "schema_name": schema_name,
                    "version": version or schema_info.version,
                    "schema_hash": schema_hash,
                    "sdl": schema_sdl,
                }
            )

        if export_format == "markdown":
            try:
                from ..introspection.documentation_generator import DocumentationGenerator
                from ..introspection.schema_introspector import SchemaIntrospection

                introspection = SchemaIntrospection.from_dict(schema_json)
                generator = DocumentationGenerator()
                markdown = generator.generate_markdown_documentation(introspection)
                return self.json_response(
                    {
                        "schema_name": schema_name,
                        "version": version or schema_info.version,
                        "schema_hash": schema_hash,
                        "markdown": markdown,
                    }
                )
            except Exception as exc:
                return self.error_response(f"Markdown export failed: {exc}", status=500)

        return self.json_response(
            {
                "schema_name": schema_name,
                "version": version or schema_info.version,
                "schema_hash": schema_hash,
                "schema": schema_json,
            }
        )


class SchemaHistoryAPIView(BaseAPIView):
    """API view for schema snapshot history."""

    auth_required = True
    rate_limit_enabled = True

    def get(self, request: HttpRequest, schema_name: str) -> JsonResponse:
        admin_check = self._require_admin(request)
        if admin_check:
            return admin_check

        if not get_setting("schema_registry.enable_schema_snapshots", False, schema_name):
            return self.error_response("Schema snapshots disabled", status=403)

        limit = request.GET.get("limit", 10)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 10

        snapshots = list_schema_snapshots(schema_name, limit=limit)
        history = [
            {
                "schema_name": snapshot.schema_name,
                "version": snapshot.version,
                "schema_hash": snapshot.schema_hash,
                "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
            }
            for snapshot in snapshots
        ]

        return self.json_response({"history": history, "count": len(history)})


class SchemaDiffAPIView(BaseAPIView):
    """API view for diffing schema snapshots."""

    auth_required = True
    rate_limit_enabled = True

    def get(self, request: HttpRequest, schema_name: str) -> JsonResponse:
        admin_check = self._require_admin(request)
        if admin_check:
            return admin_check

        if not get_setting("schema_registry.enable_schema_diff", True, schema_name):
            return self.error_response("Schema diff disabled", status=403)

        from_version = request.GET.get("from_version")
        to_version = request.GET.get("to_version")

        if from_version and to_version:
            from_snapshot = get_schema_snapshot(schema_name, version=str(from_version))
            to_snapshot = get_schema_snapshot(schema_name, version=str(to_version))
        else:
            snapshots = list_schema_snapshots(schema_name, limit=2)
            if len(snapshots) < 2:
                return self.error_response("Not enough snapshots for diff", status=400)
            to_snapshot, from_snapshot = snapshots[0], snapshots[1]

        diff = get_schema_diff(from_snapshot, to_snapshot)
        if diff is None:
            return self.error_response("Schema diff failed", status=500)

        return self.json_response(
            {
                "schema_name": schema_name,
                "from_version": getattr(from_snapshot, "version", None),
                "to_version": getattr(to_snapshot, "version", None),
                "diff": diff,
            }
        )
