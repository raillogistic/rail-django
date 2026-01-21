"""
Multi-schema GraphQL view for handling multiple GraphQL schemas with different configurations.

This module provides MultiSchemaGraphQLView, which extends the standard GraphQLView
to support dynamic schema selection, per-schema authentication, and schema-specific
configuration.
"""

import json
import logging
from typing import Any, Optional

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponseNotAllowed, JsonResponse
from django.http.multipartparser import MultiPartParserError
from django.utils.datastructures import MultiValueDict
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

try:
    import graphene
    from graphene_django.views import GraphQLView, HttpError, HttpResponseBadRequest
except ImportError:
    raise ImportError(
        "graphene-django is required for GraphQL views. "
        "Install it with: pip install graphene-django"
    )

from graphql import ExecutionResult

from .mixins import (
    AuthenticationMixin,
    IntrospectionMixin,
    QueryMixin,
    ResponseMixin,
    SchemaMixin,
)
from .utils import SchemaRegistryUnavailable

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class MultiSchemaGraphQLView(
    IntrospectionMixin,
    AuthenticationMixin,
    ResponseMixin,
    SchemaMixin,
    QueryMixin,
    GraphQLView,
):
    """
    GraphQL view that supports multiple schemas with per-schema configuration.

    This view extends the standard GraphQLView to support:
    - Dynamic schema selection based on URL parameters
    - Per-schema authentication requirements
    - Schema-specific GraphiQL configuration
    - Custom error handling per schema
    - Introspection caching for performance
    - Persisted query support

    Usage:
        from rail_django.views.graphql import MultiSchemaGraphQLView

        urlpatterns = [
            path('graphql/<str:schema_name>/', MultiSchemaGraphQLView.as_view(), name='graphql'),
        ]

    Attributes:
        _placeholder_schema: Shared placeholder schema for initialization
        _schema_cache: Per-instance schema cache (bypassed in DEBUG mode)
    """

    _placeholder_schema = None

    def __init__(self, **kwargs):
        """Initialize the multi-schema view with placeholder schema and cache."""
        if self._placeholder_schema is None:
            class _PlaceholderQuery(graphene.ObjectType):
                placeholder = graphene.String(description="Placeholder field")
            self.__class__._placeholder_schema = graphene.Schema(query=_PlaceholderQuery)

        schema = kwargs.pop("schema", None) or self._placeholder_schema
        super().__init__(schema=schema, **kwargs)
        self._schema_cache = {}

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        """
        Dispatch the request to the appropriate schema handler.

        This method validates the request, resolves the schema, checks authentication,
        configures the view, and executes the GraphQL query.

        Args:
            request: HTTP request object
            *args: Positional arguments
            **kwargs: Keyword arguments, expects 'schema_name'

        Returns:
            HttpResponse with GraphQL result or error
        """
        schema_name = kwargs.get("schema_name", "gql")
        self._schema_name = schema_name

        try:
            self._normalize_request(request)

            request_is_batch = None
            if request.method == "POST" and request.body:
                content_type = request.META.get("CONTENT_TYPE", "").lower()
                if not content_type or content_type.startswith("application/json"):
                    try:
                        parsed_body = json.loads(request.body.decode("utf-8"))
                        request_is_batch = isinstance(parsed_body, list)
                    except Exception:
                        return JsonResponse(
                            {"errors": [{"message": "Invalid JSON in request body"}]},
                            status=400)
                    persisted_response = self._apply_persisted_query(request, schema_name)
                    if persisted_response is not None:
                        return persisted_response

            schema_info = self._get_schema_info(schema_name)
            if not schema_info:
                return self._schema_not_found_response(schema_name)

            if not getattr(schema_info, "enabled", True):
                return self._schema_disabled_response(schema_name)

            graphiql_access = self._check_graphiql_access(request, schema_name, schema_info)
            if graphiql_access is not None:
                return graphiql_access

            self._configure_for_schema(schema_info)
            self._configure_middleware(schema_name)

            if (request.method == "GET" and self.graphiql and not request.GET.get("query")
                    and not self._check_authentication(request, schema_info)):
                return self._authentication_required_response()

            self.schema = self._get_schema_instance(schema_name, schema_info)

            if request.method == "GET" and not self.graphiql and not request.GET.get("query"):
                return HttpResponseNotAllowed(["POST"])

            original_batch = self.batch
            if request_is_batch is False and self.batch:
                self.batch = False
            try:
                return super().dispatch(request, *args, **kwargs)
            finally:
                self.batch = original_batch

        except SchemaRegistryUnavailable:
            return JsonResponse({"error": "Schema registry not available"}, status=503)
        except MultiPartParserError as e:
            return JsonResponse({"errors": [{"message": str(e)}]}, status=400)
        except Exception as e:
            if "Invalid boundary" in str(e):
                return JsonResponse({"errors": [{"message": "Invalid multipart boundary"}]}, status=400)
            logger.error(f"Error handling request for schema '{schema_name}': {e}")
            return self._error_response(str(e))

    def _normalize_request(self, request: HttpRequest) -> None:
        """Ensure the request object has all required attributes."""
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

    def execute_graphql_request(self, request, data, query, variables, operation_name,
                                 show_graphiql=False):
        """Execute the GraphQL request with introspection caching."""
        if not query:
            return super().execute_graphql_request(
                request, data, query, variables, operation_name, show_graphiql)

        cache_key = None
        if self._should_cache_introspection(request, query):
            schema_name = self._get_schema_name(request)
            if schema_name:
                cache_key = self._get_introspection_cache_key(schema_name)
                try:
                    cached = cache.get(cache_key)
                except Exception as exc:
                    logger.debug("Failed to read introspection cache: %s", exc)
                    cached = None
                if cached is not None:
                    return ExecutionResult(data=cached, errors=None)

        result = super().execute_graphql_request(
            request, data, query, variables, operation_name, show_graphiql)

        if cache_key and result and not result.errors and result.data is not None:
            try:
                cache.set(cache_key, result.data)
            except Exception as exc:
                logger.debug("Failed to store introspection cache: %s", exc)

        return result

    def get(self, request: HttpRequest, *args, **kwargs):
        """Handle GET requests."""
        return super().get(request, *args, **kwargs)

    def get_context(self, request):
        """Override get_context to inject authenticated user from JWT token."""
        context = super().get_context(request)

        user = self._resolve_request_user(request)
        if user and getattr(user, "is_authenticated", False):
            context.user = user
        else:
            raw_auth = request.META.get("HTTP_AUTHORIZATION", "")
            auth_header = raw_auth.strip()
            header_lower = auth_header.lower()
            if header_lower.startswith("bearer ") or header_lower.startswith("token "):
                if self._validate_token(auth_header, {}, request=request):
                    user = self._resolve_request_user(request)
                    if user and getattr(user, "is_authenticated", False):
                        context.user = user

        schema_match = getattr(request, "resolver_match", None)
        schema_name = getattr(schema_match, "kwargs", {}).get("schema_name", "gql")
        context.schema_name = schema_name

        return context

    def parse_body(self, request: HttpRequest):
        """Parse the request body, supporting single and batch JSON payloads."""
        content_type = self.get_content_type(request)

        if content_type == "application/graphql":
            return {"query": request.body.decode()}

        if content_type == "application/json":
            try:
                body = request.body.decode("utf-8")
            except Exception as exc:
                raise HttpError(HttpResponseBadRequest(str(exc)))

            try:
                request_json = json.loads(body)
                if self.batch:
                    if isinstance(request_json, list):
                        if not request_json:
                            raise HttpError(HttpResponseBadRequest(
                                "Received an empty list in the batch request."))
                        return request_json
                    if isinstance(request_json, dict):
                        return request_json
                    raise HttpError(HttpResponseBadRequest(
                        "Batch requests should receive a list or object payload."))
                if isinstance(request_json, dict):
                    return request_json
                raise HttpError(HttpResponseBadRequest(
                    "The received data is not a valid JSON query."))
            except HttpError:
                raise
            except (TypeError, ValueError):
                raise HttpError(HttpResponseBadRequest("POST body sent invalid JSON."))

        if content_type in ["application/x-www-form-urlencoded", "multipart/form-data"]:
            return request.POST

        return {}
