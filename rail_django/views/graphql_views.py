"""
Multi-schema GraphQL views for handling multiple GraphQL schemas with different configurations.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.http import HttpRequest, HttpResponseNotAllowed, JsonResponse
from django.http.multipartparser import MultiPartParserError
from django.shortcuts import render
from django.utils.datastructures import MultiValueDict
from django.utils import timezone as django_timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

try:
    import graphene
    from graphene_django.views import GraphQLView
except ImportError:
    raise ImportError(
        "graphene-django is required for GraphQL views. "
        "Install it with: pip install graphene-django"
    )

logger = logging.getLogger(__name__)


class SchemaRegistryUnavailable(Exception):
    """Raised when the schema registry cannot be accessed."""


@method_decorator(csrf_exempt, name="dispatch")
class MultiSchemaGraphQLView(GraphQLView):
    """
    GraphQL view that supports multiple schemas with per-schema configuration.

    This view extends the standard GraphQLView to support:
    - Dynamic schema selection based on URL parameters
    - Per-schema authentication requirements
    - Schema-specific GraphiQL configuration
    - Custom error handling per schema
    """

    _placeholder_schema = None

    def __init__(self, **kwargs):
        """Initialize the multi-schema view."""
        if self._placeholder_schema is None:
            class _PlaceholderQuery(graphene.ObjectType):
                placeholder = graphene.String(description="Placeholder field")

            self.__class__._placeholder_schema = graphene.Schema(
                query=_PlaceholderQuery
            )

        schema = kwargs.pop("schema", None) or self._placeholder_schema
        super().__init__(schema=schema, **kwargs)
        self._schema_cache = {}

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        """
        Dispatch the request to the appropriate schema handler.

        Args:
            request: HTTP request object
            schema_name: Name of the schema to use (from URL)
        """
        schema_name = kwargs.get("schema_name", "gql")

        try:
            if not hasattr(request, "META") or not isinstance(request.META, dict):
                request.META = {}
            if getattr(request, "content_type", None) and "CONTENT_TYPE" not in request.META:
                request.META["CONTENT_TYPE"] = request.content_type

            if not hasattr(request, "GET") or not isinstance(request.GET, (dict, MultiValueDict)):
                request.GET = {}
            if not hasattr(request, "POST") or not isinstance(request.POST, (dict, MultiValueDict)):
                request.POST = {}
            if not hasattr(request, "FILES") or not isinstance(request.FILES, (dict, MultiValueDict)):
                request.FILES = {}
            if not hasattr(request, "COOKIES") or not isinstance(request.COOKIES, dict):
                request.COOKIES = {}

            if request.method == "POST" and request.body:
                content_type = request.META.get("CONTENT_TYPE", "").lower()
                if not content_type or content_type.startswith("application/json"):
                    try:
                        json.loads(request.body.decode("utf-8"))
                    except Exception:
                        return JsonResponse(
                            {"errors": [{"message": "Invalid JSON in request body"}]},
                            status=400,
                        )
                    persisted_response = self._apply_persisted_query(
                        request, schema_name
                    )
                    if persisted_response is not None:
                        return persisted_response

            # Get schema configuration
            schema_info = self._get_schema_info(schema_name)
            if not schema_info:
                return self._schema_not_found_response(schema_name)

            # Check if schema is enabled
            if not getattr(schema_info, "enabled", True):
                return self._schema_disabled_response(schema_name)

            # Apply schema-specific configuration
            self._configure_for_schema(schema_info)

            # Apply GraphQL middleware for this schema
            self._configure_middleware(schema_name)

            if (
                request.method == "GET"
                and self.graphiql
                and not request.GET.get("query")
                and not self._check_authentication(request, schema_info)
            ):
                return self._authentication_required_response()

            # Set the schema for this request
            self.schema = self._get_schema_instance(schema_name, schema_info)

            if request.method == "GET" and not self.graphiql and not request.GET.get("query"):
                return HttpResponseNotAllowed(["POST"])

            return super().dispatch(request, *args, **kwargs)

        except SchemaRegistryUnavailable:
            return JsonResponse(
                {"error": "Schema registry not available"},
                status=503,
            )
        except MultiPartParserError as e:
            return JsonResponse(
                {"errors": [{"message": str(e)}]},
                status=400,
            )
        except Exception as e:
            if "Invalid boundary" in str(e):
                return JsonResponse(
                    {"errors": [{"message": "Invalid multipart boundary"}]},
                    status=400,
                )
            logger.error(f"Error handling request for schema '{schema_name}': {e}")
            return self._error_response(str(e))

    def get(self, request: HttpRequest, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_context(self, request):
        """
        Override get_context to inject authenticated user from JWT token.

        Args:
            request: HTTP request object

        Returns:
            Context object with authenticated user
        """
        context = super().get_context(request)

        existing_user = getattr(request, "user", None)
        if existing_user is not None and getattr(existing_user, "is_authenticated", False):
            context.user = existing_user
        else:
            # Check for JWT token authentication (case-insensitive, robust parsing)
            raw_auth = request.META.get("HTTP_AUTHORIZATION", "")
            auth_header = raw_auth.strip()
            header_lower = auth_header.lower()
            if header_lower.startswith("bearer ") or header_lower.startswith("token "):
                if self._validate_token(auth_header, {}, request=request):
                    context.user = getattr(request, "user", None)

        # Add schema name to context for metadata hierarchy
        schema_match = getattr(request, "resolver_match", None)
        schema_name = getattr(schema_match, "kwargs", {}).get("schema_name", "gql")
        context.schema_name = schema_name

        return context

    def _get_schema_info(self, schema_name: str) -> Optional[dict[str, Any]]:
        """
        Get schema information from the registry.

        Args:
            schema_name: Name of the schema

        Returns:
            Schema information dictionary or None if not found
        """
        try:
            from ..core.registry import schema_registry

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
        """
        Get or create a schema instance for the given schema name.

        Args:
            schema_name: Name of the schema
            schema_info: Schema information dictionary

        Returns:
            GraphQL schema instance
        """
        # In DEBUG mode, bypass view-level schema cache to avoid stale schemas
        if getattr(settings, "DEBUG", False):
            try:
                from ..core.registry import schema_registry

                builder = schema_registry.get_schema_builder(schema_name)
                # Always get current schema (SchemaBuilder handles rebuilds on changes)
                schema_instance = builder.get_schema()
                logger.debug(
                    f"DEBUG mode: bypassing schema cache for '{schema_name}' (version {builder.get_schema_version()})"
                )
                return schema_instance
            except Exception as e:
                logger.error(
                    f"Error getting schema instance for '{schema_name}' in DEBUG mode: {e}"
                )
                raise

        try:
            from ..core.registry import schema_registry

            schema_instance = schema_registry.get_schema_instance(schema_name)
            logger.debug(
                f"Schema instance loaded for '{schema_name}' via shared cache."
            )
            return schema_instance

        except Exception as e:
            logger.error(f"Error getting schema instance for '{schema_name}': {e}")
            raise

    def _configure_middleware(self, schema_name: str) -> None:
        """Configure the GraphQL middleware stack for this schema."""
        try:
            from ..core.middleware import get_middleware_stack
            from ..core.registry import schema_registry

            builder = schema_registry.get_schema_builder(schema_name)
            builder_middleware = list(getattr(builder, "get_middleware", lambda: [])())
            core_middleware = get_middleware_stack(schema_name)
            self.middleware = builder_middleware + core_middleware
        except Exception as e:
            logger.warning(f"Failed to configure middleware for '{schema_name}': {e}")
            self.middleware = []

    def _configure_for_schema(self, schema_info: dict[str, Any]):
        """
        Configure the view for the specific schema.

        Args:
            schema_info: Schema information dictionary
        """
        schema_settings = self._get_effective_schema_settings(schema_info)

        # Configure GraphiQL
        self.graphiql = schema_settings.get("enable_graphiql", True)

        # Configure other view settings
        if "pretty" in schema_settings:
            self.pretty = schema_settings["pretty"]

        if "batch" in schema_settings:
            self.batch = schema_settings["batch"]

    def _check_authentication(
        self, request: HttpRequest, schema_info: dict[str, Any]
    ) -> bool:
        """
        Check if the request meets authentication requirements for the schema.

        Args:
            request: HTTP request object
            schema_info: Schema information dictionary

        Returns:
            True if authentication is satisfied, False otherwise
        """
        schema_settings = self._get_effective_schema_settings(schema_info)
        auth_required = schema_settings.get("authentication_required", False)

        if not auth_required:
            return True

        # Check if user is authenticated
        if hasattr(request, "user") and request.user.is_authenticated:
            return True

        # Check for API key or token authentication
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer ") or auth_header.startswith("Token "):
            # Custom token validation logic can be added here
            return self._validate_token(auth_header, schema_settings, request=request)

        return False

    def check_schema_permissions(self, request: HttpRequest, schema_info: dict[str, Any]) -> bool:
        return self._check_authentication(request, schema_info)

    def _extract_query_text(self, request: HttpRequest) -> str:
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

    def _apply_persisted_query(
        self, request: HttpRequest, schema_name: str
    ) -> Optional[JsonResponse]:
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
            from ..extensions.persisted_queries import resolve_persisted_query
        except Exception:
            return None

        resolution = resolve_persisted_query(payload, schema_name=schema_name)
        if resolution.has_error():
            return JsonResponse(
                {
                    "errors": [
                        {
                            "message": resolution.error_message,
                            "extensions": {"code": resolution.error_code},
                        }
                    ]
                },
                status=200,
            )

        if resolution.query and payload.get("query") != resolution.query:
            payload["query"] = resolution.query
            request._body = json.dumps(payload).encode("utf-8")

        return None

    def _validate_token(
        self,
        auth_header: str,
        schema_settings: dict[str, Any],
        request: Optional[HttpRequest] = None,
    ) -> bool:
        """
        Validate authentication token for schema access.

        Args:
            auth_header: Authorization header value
            schema_settings: Schema-specific settings

        Returns:
            True if token is valid, False otherwise
        """
        try:
            # Extract token from header
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
            elif auth_header.startswith("Token "):
                token = auth_header.split(" ")[1]
            else:
                return False

            # Validate JWT token using JWTManager
            from ..extensions.auth import JWTManager

            payload = JWTManager.verify_token(token, expected_type="access")

            if not payload:
                return False

            # Check if user exists and is active
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
            # Log the error for debugging but don't expose details
            logger.warning(f"Token validation failed: {str(e)}")
            return False

    def _get_effective_schema_settings(self, schema_info: dict[str, Any]) -> dict[str, Any]:
        """Resolve schema settings using defaults plus schema overrides."""
        schema_settings = getattr(schema_info, "settings", {}) or {}
        try:
            from dataclasses import asdict
            from ..core.settings import SchemaSettings

            resolved_settings = asdict(SchemaSettings.from_schema(schema_info.name))
            return {**resolved_settings, **schema_settings}
        except Exception:
            return schema_settings

    def _allow_introspection(
        self, request: HttpRequest, schema_info: dict[str, Any]
    ) -> bool:
        """Return False when introspection is disabled and query uses it."""
        schema_settings = self._get_effective_schema_settings(schema_info)
        enable_introspection = schema_settings.get("enable_introspection", True)
        user = getattr(request, "user", None)
        try:
            from ..core.security import is_introspection_allowed

            if is_introspection_allowed(
                user,
                getattr(schema_info, "name", None),
                enable_introspection=bool(enable_introspection),
            ):
                return True
        except Exception:
            if enable_introspection:
                return True

        query_text = self._extract_query_text(request)

        if "__schema" in query_text or "__type" in query_text:
            self._audit_introspection_attempt(request, schema_info, query_text)
            return False

        return True

    def _audit_introspection_attempt(
        self, request: HttpRequest, schema_info: dict[str, Any], query_text: str
    ) -> None:
        try:
            from ..security.audit_logging import (
                AuditEvent,
                AuditEventType,
                AuditSeverity,
                audit_logger,
                get_client_ip,
            )
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

    def _introspection_disabled_response(self) -> JsonResponse:
        """Return a 403 response when introspection is disabled."""
        return JsonResponse(
            {
                "errors": [
                    {
                        "message": "Introspection is disabled for this schema",
                        "extensions": {"code": "INTROSPECTION_DISABLED"},
                    }
                ]
            },
            status=403,
        )

    def _schema_not_found_response(self, schema_name: str) -> JsonResponse:
        """Return a 404 response for unknown schemas."""
        return JsonResponse(
            {
                "errors": [
                    {
                        "message": f"Schema '{schema_name}' not found",
                        "extensions": {
                            "code": "SCHEMA_NOT_FOUND",
                            "schema_name": schema_name,
                        },
                    }
                ]
            },
            status=404,
        )

    def _schema_disabled_response(self, schema_name: str) -> JsonResponse:
        """Return a 403 response for disabled schemas."""
        return JsonResponse(
            {
                "errors": [
                    {
                        "message": f"Schema '{schema_name}' is currently disabled",
                        "extensions": {
                            "code": "SCHEMA_DISABLED",
                            "schema_name": schema_name,
                        },
                    }
                ]
            },
            status=403,
        )

    def _authentication_required_response(self) -> JsonResponse:
        """Return a 401 response for authentication failures."""
        return JsonResponse(
            {
                "errors": [
                    {
                        "message": "Authentication required for this schema",
                        "extensions": {"code": "authentication_required"},
                    }
                ]
            },
            status=200,
        )

    def _error_response(self, error_message: str) -> JsonResponse:
        """Return a 500 response for internal errors."""
        return JsonResponse(
            {
                "errors": [
                    {
                        "message": "Internal server error",
                        "extensions": {
                            "code": "INTERNAL_ERROR",
                            "details": error_message if settings.DEBUG else None,
                        },
                    }
                ]
            },
            status=500,
        )


class SchemaListView(View):
    """
    View for listing available GraphQL schemas and their metadata.
    """

    template_name = "schema_registry.html"

    def get(self, request: HttpRequest) -> JsonResponse:
        """Return available schemas as JSON or a rendered HTML page."""
        wants_html = self._wants_html(request)
        try:
            from ..core.registry import schema_registry

            schema_registry.discover_schemas()
            schemas = self._serialize_schemas(schema_registry.list_schemas())

            if wants_html:
                return render(
                    request,
                    self.template_name,
                    self._build_context(schemas),
                )

            return JsonResponse({"schemas": schemas, "count": len(schemas)})

        except ImportError:
            if wants_html:
                context = self._build_context([])
                context["error"] = "Schema registry not available"
                return render(request, self.template_name, context, status=503)

            return JsonResponse({"error": "Schema registry not available"}, status=503)
        except Exception as e:
            logger.error(f"Error listing schemas: {e}")
            if wants_html:
                context = self._build_context([])
                context["error"] = "Failed to list schemas"
                return render(request, self.template_name, context, status=500)

            return JsonResponse({"error": "Failed to list schemas"}, status=500)

    def _serialize_schemas(self, schema_list) -> list[dict[str, Any]]:
        schemas = []
        for schema_info in schema_list:
            if not schema_info:
                continue
            settings_dict = getattr(schema_info, "settings", {}) or {}
            schema_settings = settings_dict.get("schema_settings", {})
            if not isinstance(schema_settings, dict):
                schema_settings = {}
            raw_models = getattr(schema_info, "models", []) or []
            if isinstance(raw_models, (list, tuple, set)):
                models = list(raw_models)
            else:
                models = []
            public_info = {
                "name": getattr(schema_info, "name", ""),
                "description": getattr(schema_info, "description", ""),
                "version": getattr(schema_info, "version", "1.0.0"),
                "enabled": getattr(schema_info, "enabled", True),
                "graphiql_enabled": schema_settings.get(
                    "enable_graphiql",
                    settings_dict.get("enable_graphiql", True),
                ),
                "authentication_required": schema_settings.get(
                    "authentication_required",
                    settings_dict.get("authentication_required", False),
                ),
                "models": models,
            }
            schemas.append(public_info)
        return schemas

    def _build_context(self, schemas: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(schemas)
        enabled = sum(1 for schema in schemas if schema.get("enabled"))
        graphiql_enabled = sum(
            1 for schema in schemas if schema.get("graphiql_enabled")
        )
        auth_required = sum(
            1 for schema in schemas if schema.get("authentication_required")
        )
        return {
            "schemas": schemas,
            "counts": {
                "total": total,
                "enabled": enabled,
                "disabled": total - enabled,
                "graphiql_enabled": graphiql_enabled,
                "auth_required": auth_required,
            },
        }

    def _wants_html(self, request: HttpRequest) -> bool:
        format_param = str(request.GET.get("format", "") or "").lower()
        if format_param == "json":
            return False
        if format_param == "html":
            return True

        accept = str(request.META.get("HTTP_ACCEPT", "") or "")
        return "text/html" in accept.lower()
