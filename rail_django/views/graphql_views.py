"""
Multi-schema GraphQL views for handling multiple GraphQL schemas with different configurations.
"""

import json
import logging
from typing import Any, Dict, Optional

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone as django_timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

try:
    from graphene_django.views import GraphQLView
    from graphql import GraphQLError
except ImportError:
    raise ImportError(
        "graphene-django is required for GraphQL views. "
        "Install it with: pip install graphene-django"
    )

logger = logging.getLogger(__name__)


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

    def __init__(self, **kwargs):
        """Initialize the multi-schema view."""
        super().__init__(**kwargs)
        self._schema_cache = {}

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        """
        Dispatch the request to the appropriate schema handler.

        Args:
            request: HTTP request object
            schema_name: Name of the schema to use (from URL)
        """
        schema_name = kwargs.get("schema_name", "default")

        try:
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

            # Check authentication requirements
            if not self._check_authentication(request, schema_info):
                return self._authentication_required_response()

            # Enforce introspection settings
            if not self._allow_introspection(request, schema_info):
                return self._introspection_disabled_response()

            # Set the schema for this request
            self.schema = self._get_schema_instance(schema_name, schema_info)

            return super().dispatch(request, *args, **kwargs)

        except Exception as e:
            logger.error(f"Error handling request for schema '{schema_name}': {e}")
            return self._error_response(str(e))

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
        schema_name = getattr(schema_match, "kwargs", {}).get("schema_name", "default")
        context.schema_name = schema_name

        return context

    def _get_schema_info(self, schema_name: str) -> Optional[Dict[str, Any]]:
        """
        Get schema information from the registry.

        Args:
            schema_name: Name of the schema

        Returns:
            Schema information dictionary or None if not found
        """
        try:
            from ..core.registry import schema_registry

            return schema_registry.get_schema(schema_name)
        except ImportError:
            logger.warning("Schema registry not available")
            return None
        except Exception as e:
            logger.error(f"Error getting schema info for '{schema_name}': {e}")
            return None

    def _get_schema_instance(self, schema_name: str, schema_info: Dict[str, Any]):
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

    def _configure_for_schema(self, schema_info: Dict[str, Any]):
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
        self, request: HttpRequest, schema_info: Dict[str, Any]
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

    def _validate_token(
        self,
        auth_header: str,
        schema_settings: Dict[str, Any],
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

    def _get_effective_schema_settings(self, schema_info: Dict[str, Any]) -> Dict[str, Any]:
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
        self, request: HttpRequest, schema_info: Dict[str, Any]
    ) -> bool:
        """Return False when introspection is disabled and query uses it."""
        schema_settings = self._get_effective_schema_settings(schema_info)
        if schema_settings.get("enable_introspection", True):
            return True

        query_text = ""
        if request.method == "GET":
            query_text = request.GET.get("query", "")
        elif request.body:
            try:
                body = json.loads(request.body.decode("utf-8"))
                query_text = body.get("query", "") or ""
            except Exception:
                query_text = ""

        if "__schema" in query_text or "__type" in query_text:
            self._audit_introspection_attempt(request, schema_info, query_text)
            return False

        return True

    def _audit_introspection_attempt(
        self, request: HttpRequest, schema_info: Dict[str, Any], query_text: str
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
        """Return a 503 response for disabled schemas."""
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
            status=503,
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
            status=401,
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

    def get(self, request: HttpRequest) -> JsonResponse:
        """
        Return a list of available schemas with their metadata.

        Returns:
            JSON response with schema list
        """
        try:
            from ..core.registry import schema_registry

            schemas = []
            for schema_info in schema_registry.list_schemas():
                if schema_info:
                    settings_dict = getattr(schema_info, "settings", {}) or {}
                    public_info = {
                        "name": getattr(schema_info, "name", ""),
                        "description": getattr(schema_info, "description", ""),
                        "version": getattr(schema_info, "version", "1.0.0"),
                        "enabled": getattr(schema_info, "enabled", True),
                        "graphiql_enabled": settings_dict.get("enable_graphiql", True),
                        "authentication_required": settings_dict.get(
                            "authentication_required", False
                        ),
                    }
                    schemas.append(public_info)

            return JsonResponse({"schemas": schemas, "count": len(schemas)})

        except ImportError:
            return JsonResponse({"error": "Schema registry not available"}, status=503)
        except Exception as e:
            logger.error(f"Error listing schemas: {e}")
            return JsonResponse({"error": "Failed to list schemas"}, status=500)


class GraphQLPlaygroundView(View):
    """
    Custom GraphQL Playground view with schema-specific configuration.
    """

    def get(self, request: HttpRequest, schema_name: str = "default") -> HttpResponse:
        """
        Render GraphQL Playground for the specified schema.

        Args:
            request: HTTP request object
            schema_name: Name of the schema

        Returns:
            HTML response with GraphQL Playground
        """
        try:
            from ..core.registry import schema_registry

            # Get schema info
            schema_info = schema_registry.get_schema(schema_name)
            if not schema_info:
                raise Http404(f"Schema '{schema_name}' not found")

            # Check if GraphiQL is enabled for this schema
            schema_settings = getattr(schema_info, "settings", {}) or {}
            try:
                from dataclasses import asdict
                from ..core.settings import SchemaSettings

                resolved_settings = asdict(SchemaSettings.from_schema(schema_name))
                schema_settings = {**resolved_settings, **schema_settings}
            except Exception:
                pass
            if not schema_settings.get("enable_graphiql", True):
                return HttpResponse(
                    f"GraphQL Playground is disabled for schema '{schema_name}'",
                    status=403,
                )

            # Generate playground HTML
            playground_html = self._generate_playground_html(schema_name, schema_info)
            return HttpResponse(playground_html, content_type="text/html")

        except ImportError:
            return HttpResponse("Schema registry not available", status=503)
        except Exception as e:
            logger.error(f"Error rendering playground for schema '{schema_name}': {e}")
            return HttpResponse("Failed to load GraphQL Playground", status=500)

    def _generate_playground_html(
        self, schema_name: str, schema_info: Dict[str, Any]
    ) -> str:
        """
        Generate HTML for GraphQL Playground.

        Args:
            schema_name: Name of the schema
            schema_info: Schema information dictionary

        Returns:
            HTML string for the playground
        """
        endpoint_url = f"/graphql/{schema_name}/"
        schema_description = getattr(
            schema_info, "description", f"GraphQL Playground for {schema_name}"
        )

        playground_version = "1.7.28"
        playground_base = (
            f"https://cdn.jsdelivr.net/npm/graphql-playground-react@{playground_version}/build"
        )
        css_sri = (
            "sha384-xb+UHILNN4fV3NgQMTjXk0x9A80U0hmkraTFvucUYTILJymGT8E1Aq2278NSi5+3"
        )
        js_sri = (
            "sha384-ardaO17esJ2ZxvY24V1OE6X4j+Z3WKgGMptrlDLmD+2w/JC3nbQ5ZfKGY2zfOPEE"
        )

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>{schema_description}</title>
            <link rel="stylesheet" href="{playground_base}/static/css/index.css" integrity="{css_sri}" crossorigin="anonymous" />
            <link rel="shortcut icon" href="{playground_base}/favicon.png" />
            <script src="{playground_base}/static/js/middleware.js" integrity="{js_sri}" crossorigin="anonymous"></script>
        </head>
        <body>
            <div id="root">
                <style>
                    body {{ background: rgb(23, 42, 58); font-family: Open Sans, sans-serif; height: 90vh; }}
                    #root {{ height: 100%; width: 100%; display: flex; align-items: center; justify-content: center; }}
                    .loading {{ font-size: 32px; font-weight: 200; color: rgba(255, 255, 255, .6); margin-left: 20px; }}
                    img {{ width: 78px; height: 78px; }}
                    .title {{ font-weight: 400; }}
                </style>
                <img src="{playground_base}/logo.png" alt="" />
                <div class="loading"> Loading
                    <span class="title">GraphQL Playground</span>
                </div>
            </div>
            <script>
                window.addEventListener('load', function (event) {{
                    GraphQLPlayground.init(document.getElementById('root'), {{
                        endpoint: '{endpoint_url}',
                        settings: {{
                            'general.betaUpdates': false,
                            'editor.theme': 'dark',
                            'editor.reuseHeaders': true,
                            'tracing.hideTracingResponse': true,
                            'editor.fontSize': 14,
                            'editor.fontFamily': '"Source Code Pro", "Consolas", "Inconsolata", "Droid Sans Mono", "Monaco", monospace',
                            'request.credentials': 'omit',
                        }},
                        tabs: [{{
                            endpoint: '{endpoint_url}',
                            query: '# Welcome to GraphQL Playground for {schema_name}\\n# {schema_description}\\n\\n{{\\n  __schema {{\\n    types {{\\n      name\\n    }}\\n  }}\\n}}',
                        }}],
                    }})
                }})
            </script>
        </body>
        </html>
        """
