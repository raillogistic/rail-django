"""
Mixin classes for MultiSchemaGraphQLView.

Mixins:
    ResponseMixin: HTTP response generation for error conditions
    AuthenticationMixin: User authentication and token validation
    SchemaMixin: Schema loading and configuration
    IntrospectionMixin: Introspection query handling and caching
    QueryMixin: Query extraction and persisted query handling
"""

import json
import logging
from typing import Any, Optional

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils import timezone as django_timezone

from graphql import parse
from graphql.language.ast import FieldNode, OperationDefinitionNode

from .utils import INTROSPECTION_FIELDS, _get_authenticated_user, _host_allowed

logger = logging.getLogger(__name__)


class ResponseMixin:
    """Mixin providing HTTP response generation for various error conditions."""

    def _introspection_disabled_response(self) -> JsonResponse:
        """Return a 403 response when introspection is disabled."""
        return JsonResponse(
            {"errors": [{"message": "Introspection is disabled for this schema",
                         "extensions": {"code": "INTROSPECTION_DISABLED"}}]},
            status=403)

    def _schema_not_found_response(self, schema_name: str) -> JsonResponse:
        """Return a 404 response for unknown schemas."""
        return JsonResponse(
            {"errors": [{"message": f"Schema '{schema_name}' not found",
                         "extensions": {"code": "SCHEMA_NOT_FOUND", "schema_name": schema_name}}]},
            status=404)

    def _schema_disabled_response(self, schema_name: str) -> JsonResponse:
        """Return a 403 response for disabled schemas."""
        return JsonResponse(
            {"errors": [{"message": f"Schema '{schema_name}' is currently disabled",
                         "extensions": {"code": "SCHEMA_DISABLED", "schema_name": schema_name}}]},
            status=403)

    def _authentication_required_response(self) -> JsonResponse:
        """Return a 401 response for authentication failures."""
        return JsonResponse(
            {"errors": [{"message": "Authentication required for this schema",
                         "extensions": {"code": "authentication_required"}}]},
            status=200)

    def _error_response(self, error_message: str) -> JsonResponse:
        """Return a 500 response for internal errors."""
        return JsonResponse(
            {"errors": [{"message": "Internal server error",
                         "extensions": {"code": "INTERNAL_ERROR",
                                        "details": error_message if settings.DEBUG else None}}]},
            status=500)


class AuthenticationMixin:
    """Mixin providing authentication and authorization functionality."""

    def _resolve_request_user(self, request: HttpRequest):
        """Resolve and attach the authenticated user to the request."""
        user = _get_authenticated_user(request)
        if user is not None:
            try:
                request.user = user
            except Exception:
                pass
        return user

    def _check_authentication(self, request: HttpRequest, schema_info: dict[str, Any]) -> bool:
        """Check if the request meets authentication requirements for the schema."""
        schema_settings = self._get_effective_schema_settings(schema_info)
        auth_required = schema_settings.get("authentication_required", False)
        superuser_only = bool(
            schema_settings.get("graphiql_superuser_only", False)
            and str(getattr(schema_info, "name", "")).lower() == "graphiql")

        user = self._resolve_request_user(request)
        if user and getattr(user, "is_authenticated", False):
            if superuser_only and not getattr(user, "is_superuser", False):
                return False
            return True

        if not auth_required and not superuser_only:
            return True

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer ") or auth_header.startswith("Token "):
            if self._validate_token(auth_header, schema_settings, request=request):
                user = self._resolve_request_user(request)
                if superuser_only and not (user and getattr(user, "is_superuser", False)):
                    return False
                return True
        return False

    def check_schema_permissions(self, request: HttpRequest, schema_info: dict[str, Any]) -> bool:
        """Check if the request has permissions for the schema."""
        return self._check_authentication(request, schema_info)

    def _validate_token(self, auth_header: str, schema_settings: dict[str, Any],
                        request: Optional[HttpRequest] = None) -> bool:
        """Validate authentication token for schema access."""
        try:
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
            elif auth_header.startswith("Token "):
                token = auth_header.split(" ")[1]
            else:
                return False

            from ...extensions.auth import JWTManager
            payload = JWTManager.verify_token(token, expected_type="access")
            if not payload:
                return False

            user_id = payload.get("user_id") or payload.get("sub")
            if not user_id:
                return False

            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.filter(id=user_id, is_active=True).first()
            if not user:
                return False

            if request is not None:
                request.user = user
                request.jwt_payload = payload
            return True
        except Exception as e:
            logger.warning(f"Token validation failed: {str(e)}")
            return False


class SchemaMixin:
    """Mixin providing schema loading and configuration functionality."""

    def _get_schema_info(self, schema_name: str) -> Optional[dict[str, Any]]:
        """Get schema information from the registry."""
        from .utils import SchemaRegistryUnavailable
        try:
            from ...core.registry import schema_registry
            schema_registry.discover_schemas()
            return schema_registry.get_schema(schema_name)
        except ImportError as exc:
            logger.warning("Schema registry not available")
            raise SchemaRegistryUnavailable(str(exc))
        except Exception as e:
            logger.error(f"Error getting schema info for '{schema_name}': {e}")
            if isinstance(e, ImportError):
                raise SchemaRegistryUnavailable(str(e))
            return None

    def _get_schema_instance(self, schema_name: str, schema_info: dict[str, Any]):
        """Get or create a schema instance for the given schema name."""
        if getattr(settings, "DEBUG", False):
            try:
                from ...core.registry import schema_registry
                builder = schema_registry.get_schema_builder(schema_name)
                schema_instance = builder.get_schema()
                logger.debug(f"DEBUG mode: bypassing schema cache for '{schema_name}' "
                             f"(version {builder.get_schema_version()})")
                return schema_instance
            except Exception as e:
                logger.error(f"Error getting schema instance for '{schema_name}' in DEBUG mode: {e}")
                raise

        try:
            from ...core.registry import schema_registry
            schema_instance = schema_registry.get_schema_instance(schema_name)
            logger.debug(f"Schema instance loaded for '{schema_name}' via shared cache.")
            return schema_instance
        except Exception as e:
            logger.error(f"Error getting schema instance for '{schema_name}': {e}")
            raise

    def _configure_middleware(self, schema_name: str) -> None:
        """Configure the GraphQL middleware stack for this schema."""
        try:
            from ...core.middleware import get_middleware_stack
            from ...core.registry import schema_registry
            builder = schema_registry.get_schema_builder(schema_name)
            builder_middleware = list(getattr(builder, "get_middleware", lambda: [])())
            core_middleware = get_middleware_stack(schema_name)
            self.middleware = builder_middleware + core_middleware
        except Exception as e:
            logger.warning(f"Failed to configure middleware for '{schema_name}': {e}")
            self.middleware = []

    def _configure_for_schema(self, schema_info: dict[str, Any]) -> None:
        """Configure the view for the specific schema."""
        schema_settings = self._get_effective_schema_settings(schema_info)
        self.graphiql = schema_settings.get("enable_graphiql", True)
        if "pretty" in schema_settings:
            self.pretty = schema_settings["pretty"]
        if "batch" in schema_settings:
            self.batch = schema_settings["batch"]

    def _get_effective_schema_settings(self, schema_info: dict[str, Any]) -> dict[str, Any]:
        """Resolve schema settings using defaults plus schema overrides."""
        schema_settings = getattr(schema_info, "settings", {}) or {}
        try:
            from dataclasses import asdict
            from ...core.settings import SchemaSettings
            resolved_settings = asdict(SchemaSettings.from_schema(schema_info.name))
            return {**resolved_settings, **schema_settings}
        except Exception:
            return schema_settings

    def _check_graphiql_access(self, request: HttpRequest, schema_name: str,
                                schema_info: dict[str, Any]) -> Optional[JsonResponse]:
        """Check if the request has access to GraphiQL for this schema."""
        if str(schema_name).lower() != "graphiql":
            return None

        schema_settings = self._get_effective_schema_settings(schema_info)
        allowed_hosts = schema_settings.get("graphiql_allowed_hosts") or []
        if not isinstance(allowed_hosts, (list, tuple, set)):
            allowed_hosts = [str(allowed_hosts)]
        if not _host_allowed(request, list(allowed_hosts)):
            return self._schema_not_found_response(schema_name)

        if schema_settings.get("graphiql_superuser_only", False):
            if not self._check_authentication(request, schema_info):
                return JsonResponse(
                    {"errors": [{"message": "Superuser access required",
                                 "extensions": {"code": "superuser_required"}}]},
                    status=403)
        return None


class IntrospectionMixin:
    """Mixin providing introspection query handling and caching."""

    def _get_schema_name(self, request: HttpRequest) -> str:
        """Extract the schema name from the request."""
        schema_name = getattr(self, "_schema_name", None)
        if schema_name:
            return schema_name
        schema_match = getattr(request, "resolver_match", None)
        if schema_match:
            return getattr(schema_match, "kwargs", {}).get("schema_name", "gql")
        return "gql"

    def _is_introspection_query(self, query: str) -> bool:
        """Check if a query is an introspection query."""
        try:
            document = parse(query)
        except Exception:
            return False

        found_operation = False
        for definition in document.definitions:
            if not isinstance(definition, OperationDefinitionNode):
                continue
            found_operation = True
            selections = getattr(definition.selection_set, "selections", None) or []
            if not selections:
                return False
            for selection in selections:
                if isinstance(selection, FieldNode):
                    if selection.name.value not in INTROSPECTION_FIELDS:
                        return False
                else:
                    return False
        return found_operation

    def _should_cache_introspection(self, request: HttpRequest, query: str) -> bool:
        """Determine if an introspection query result should be cached."""
        if getattr(settings, "DEBUG", False):
            return False
        if not self._is_introspection_query(query):
            return False

        schema_name = self._get_schema_name(request)
        if not schema_name:
            return False
        try:
            from ...core.security import is_introspection_allowed
            from ...core.settings import SchemaSettings
        except Exception:
            return False

        schema_settings = SchemaSettings.from_schema(schema_name)
        user = self._resolve_request_user(request)
        if schema_settings.authentication_required:
            if not user or not getattr(user, "is_authenticated", False):
                return False
        if not is_introspection_allowed(user, schema_name,
                                         enable_introspection=schema_settings.enable_introspection):
            return False
        return True

    def _get_introspection_cache_key(self, schema_name: str) -> str:
        """Generate a cache key for introspection results."""
        version = "0"
        try:
            from ...core.registry import schema_registry
            builder = schema_registry.get_schema_builder(schema_name)
            version = str(builder.get_schema_version())
        except Exception:
            version = "0"
        return f"rail_django:introspection:{schema_name}:{version}"

    def _allow_introspection(self, request: HttpRequest, schema_info: dict[str, Any]) -> bool:
        """Check if introspection is allowed for the current request."""
        schema_settings = self._get_effective_schema_settings(schema_info)
        enable_introspection = schema_settings.get("enable_introspection", True)
        user = getattr(request, "user", None)
        try:
            from ...core.security import is_introspection_allowed
            if is_introspection_allowed(user, getattr(schema_info, "name", None),
                                         enable_introspection=bool(enable_introspection)):
                return True
        except Exception:
            if enable_introspection:
                return True

        query_text = self._extract_query_text(request)
        if "__schema" in query_text or "__type" in query_text:
            self._audit_introspection_attempt(request, schema_info, query_text)
            return False
        return True

    def _audit_introspection_attempt(self, request: HttpRequest, schema_info: dict[str, Any],
                                      query_text: str) -> None:
        """Log an audit event for a blocked introspection attempt."""
        try:
            from ...security.audit_logging import (
                AuditEvent, AuditEventType, AuditSeverity, audit_logger, get_client_ip)
        except Exception:
            return

        user = getattr(request, "user", None)
        details = {
            "schema_name": getattr(schema_info, "name", None),
            "request_path": getattr(request, "path", None),
            "request_method": getattr(request, "method", None),
            "query_length": len(query_text or ""),
        }
        event = AuditEvent(
            event_type=AuditEventType.INTROSPECTION_ATTEMPT,
            severity=AuditSeverity.WARNING,
            timestamp=django_timezone.now(),
            user_id=user.id if user and user.is_authenticated else None,
            username=user.username if user and user.is_authenticated else None,
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT"),
            message="Introspection disabled for schema",
            details=details,
        )
        audit_logger.log_event(event)


class QueryMixin:
    """Mixin providing query extraction and persisted query handling."""

    def _extract_query_text(self, request: HttpRequest) -> str:
        """Extract the query text from a request."""
        if request.method == "GET":
            query = request.GET.get("query", "")
            return str(query) if query is not None else ""
        if not request.body:
            return ""
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return ""
        if isinstance(body, dict):
            query = body.get("query", "")
            return str(query) if query is not None else ""
        return ""

    def _apply_persisted_query(self, request: HttpRequest,
                                schema_name: str) -> Optional[JsonResponse]:
        """Apply persisted query resolution to a request."""
        if request.method != "POST" or not request.body:
            return None

        content_type = request.META.get("CONTENT_TYPE", "").lower()
        if content_type and not content_type.startswith("application/json"):
            return None

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            return None

        if not isinstance(payload, dict):
            return None

        try:
            from ...extensions.persisted_queries import resolve_persisted_query
        except Exception:
            return None

        resolution = resolve_persisted_query(payload, schema_name=schema_name)
        if resolution.has_error():
            return JsonResponse(
                {"errors": [{"message": resolution.error_message,
                             "extensions": {"code": resolution.error_code}}]},
                status=200)

        if resolution.query and payload.get("query") != resolution.query:
            payload["query"] = resolution.query
            request._body = json.dumps(payload).encode("utf-8")
        return None


__all__ = ["ResponseMixin", "AuthenticationMixin", "SchemaMixin", "IntrospectionMixin", "QueryMixin"]
