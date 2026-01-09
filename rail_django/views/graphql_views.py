"""
Multi-schema GraphQL views for handling multiple GraphQL schemas with different configurations.
"""

import json
import logging
from typing import Any, Dict, Optional

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
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

            # Check authentication requirements
            if not self._check_authentication(request, schema_info):
                return self._authentication_required_response()

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

        # Check for JWT token authentication (case-insensitive, robust parsing)
        raw_auth = request.META.get("HTTP_AUTHORIZATION", "")
        auth_header = raw_auth.strip()
        header_lower = auth_header.lower()
        if header_lower.startswith("bearer ") or header_lower.startswith("token "):
            try:
                # Extract token from header
                parts = auth_header.split(" ", 1)
                token = parts[1] if len(parts) == 2 else None
                if token:
                    # Validate JWT token using JWTManager
                    from ..extensions.auth import JWTManager

                    payload = JWTManager.verify_token(token)

                    if payload:
                        # Get user from payload, support standard 'sub' claim fallback
                        user_id = payload.get("user_id") or payload.get("sub")
                        if user_id:
                            from django.contrib.auth import get_user_model

                            User = get_user_model()

                            user = User.objects.filter(id=user_id, is_active=True).first()
                            if user:
                                # Inject authenticated user into context
                                context.user = user
                                # Also set on request for compatibility
                                request.user = user
            except Exception as e:
                # Log the error for debugging but don't expose details
                logger.warning(f"JWT authentication failed: {str(e)}")

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

            builder = schema_registry.get_schema_builder(schema_name)
            current_version = getattr(builder, "get_schema_version", lambda: 0)()

            # If cached and version matches, return cached instance
            cached_entry = self._schema_cache.get(schema_name)
            if isinstance(cached_entry, dict):
                cached_version = cached_entry.get("version", -1)
                if cached_version == current_version:
                    return cached_entry.get("schema")
            elif cached_entry is not None:
                # Backward compatibility: cached plain instance without version
                # Refresh cache to include version metadata
                schema_instance = builder.get_schema()
                self._schema_cache[schema_name] = {
                    "version": current_version,
                    "schema": schema_instance,
                }
                logger.debug(
                    f"Initialized versioned schema cache for '{schema_name}' (version {current_version})"
                )
                return schema_instance

            # Not cached or version mismatch: fetch and cache fresh instance
            schema_instance = builder.get_schema()
            self._schema_cache[schema_name] = {
                "version": current_version,
                "schema": schema_instance,
            }
            logger.debug(
                f"Schema cache refreshed for '{schema_name}' (version {current_version})"
            )
            return schema_instance

        except Exception as e:
            logger.error(f"Error getting schema instance for '{schema_name}': {e}")
            raise

    def _configure_for_schema(self, schema_info: Dict[str, Any]):
        """
        Configure the view for the specific schema.

        Args:
            schema_info: Schema information dictionary
        """
        schema_settings = getattr(schema_info, "settings", {}) or {}

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
        schema_settings = getattr(schema_info, "settings", {}) or {}
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
            return self._validate_token(auth_header, schema_settings)

        return False

    def _validate_token(
        self, auth_header: str, schema_settings: Dict[str, Any]
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

            payload = JWTManager.verify_token(token)

            if not payload:
                return False

            # Check if user exists and is active
            user_id = payload.get("user_id")
            if not user_id:
                return False

            from django.contrib.auth import get_user_model

            User = get_user_model()

            try:
                user = User.objects.get(id=user_id)
                return user.is_active
            except User.DoesNotExist:
                return False

        except Exception as e:
            # Log the error for debugging but don't expose details
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Token validation failed: {str(e)}")
            return False

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

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>{schema_description}</title>
            <link rel="stylesheet" href="//cdn.jsdelivr.net/npm/graphql-playground-react/build/static/css/index.css" />
            <link rel="shortcut icon" href="//cdn.jsdelivr.net/npm/graphql-playground-react/build/favicon.png" />
            <script src="//cdn.jsdelivr.net/npm/graphql-playground-react/build/static/js/middleware.js"></script>
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
                <img src="//cdn.jsdelivr.net/npm/graphql-playground-react/build/logo.png" alt="" />
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
