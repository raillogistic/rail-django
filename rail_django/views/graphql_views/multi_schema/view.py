"""
MultiSchemaGraphQLView implementation.
"""

import json
import logging
from typing import Any, Optional

import graphene
from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponseNotAllowed, JsonResponse
from django.http.multipartparser import MultiPartParserError
from django.utils.datastructures import MultiValueDict
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

try:
    from graphene_django.views import GraphQLView, HttpError, HttpResponseBadRequest
except ImportError:
    raise ImportError(
        "graphene-django is required for GraphQL views. Install it with: pip install graphene-django"
    )

from graphql import ExecutionResult

from ..utils import (
    _get_effective_schema_settings,
    _host_allowed,
)
from .authentication import AuthenticationMixin
from .introspection import IntrospectionMixin
from .responses import ResponseMixin

logger = logging.getLogger(__name__)


class SchemaRegistryUnavailable(Exception):
    """Raised when the schema registry cannot be accessed."""


@method_decorator(csrf_exempt, name="dispatch")
class MultiSchemaGraphQLView(AuthenticationMixin, IntrospectionMixin, ResponseMixin, GraphQLView):
    """
    GraphQL view that supports multiple schemas with per-schema configuration.
    """

    _placeholder_schema = None

    def __init__(self, **kwargs):
        if self._placeholder_schema is None:
            class _PlaceholderQuery(graphene.ObjectType):
                placeholder = graphene.String(description="Placeholder field")
            self.__class__._placeholder_schema = graphene.Schema(query=_PlaceholderQuery)

        schema = kwargs.pop("schema", None) or self._placeholder_schema
        super().__init__(schema=schema, **kwargs)
        self._schema_cache = {}

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        schema_name = kwargs.get("schema_name", "gql")
        self._schema_name = schema_name

        try:
            if not hasattr(request, "META") or not isinstance(request.META, dict): request.META = {}
            if getattr(request, "content_type", None) and "CONTENT_TYPE" not in request.META:
                request.META["CONTENT_TYPE"] = request.content_type

            if not hasattr(request, "GET") or not isinstance(request.GET, (dict, MultiValueDict)): request.GET = {}
            if not hasattr(request, "POST") or not isinstance(request.POST, (dict, MultiValueDict)): request.POST = {}
            if not hasattr(request, "FILES") or not isinstance(request.FILES, (dict, MultiValueDict)): request.FILES = {}
            if not hasattr(request, "COOKIES") or not isinstance(request.COOKIES, dict): request.COOKIES = {}

            request_is_batch = None
            if request.method == "POST" and request.body:
                content_type = request.META.get("CONTENT_TYPE", "").lower()
                if not content_type or content_type.startswith("application/json"):
                    try:
                        parsed_body = json.loads(request.body.decode("utf-8"))
                        request_is_batch = isinstance(parsed_body, list)
                    except Exception:
                        return JsonResponse({"errors": [{"message": "Invalid JSON in request body"}]}, status=400)
                    persisted_response = self._apply_persisted_query(request, schema_name)
                    if persisted_response is not None: return persisted_response

            schema_info = self._get_schema_info(schema_name)
            if not schema_info: return self._schema_not_found_response(schema_name)
            if not getattr(schema_info, "enabled", True): return self._schema_disabled_response(schema_name)

            graphiql_access = self._check_graphiql_access(request, schema_name, schema_info)
            if graphiql_access is not None: return graphiql_access

            self._configure_for_schema(schema_info)
            self._configure_middleware(schema_name)

            if (request.method == "GET" and self.graphiql and not request.GET.get("query")
                and not self._check_authentication(request, schema_info)):
                return self._authentication_required_response()

            self.schema = self._get_schema_instance(schema_name, schema_info)
            if request.method == "GET" and not self.graphiql and not request.GET.get("query"):
                return HttpResponseNotAllowed(["POST"])

            original_batch = self.batch
            if request_is_batch is False and self.batch: self.batch = False
            try: return super().dispatch(request, *args, **kwargs)
            finally: self.batch = original_batch

        except SchemaRegistryUnavailable:
            return JsonResponse({"error": "Schema registry not available"}, status=503)
        except MultiPartParserError as e:
            return JsonResponse({"errors": [{"message": str(e)}]}, status=400)
        except Exception as e:
            if "Invalid boundary" in str(e):
                return JsonResponse({"errors": [{"message": "Invalid multipart boundary"}]}, status=400)
            logger.error(f"Error handling request for schema '{schema_name}': {e}")
            return self._error_response(str(e))

    def execute_graphql_request(self, request, data, query, variables, operation_name, show_graphiql=False):
        if not query: return super().execute_graphql_request(request, data, query, variables, operation_name, show_graphiql)
        cache_key = None
        if self._should_cache_introspection(request, query):
            schema_name = self._get_schema_name(request)
            if schema_name:
                cache_key = self._get_introspection_cache_key(schema_name)
                try: cached = cache.get(cache_key)
                except Exception as exc: logger.debug("Failed to read introspection cache: %s", exc); cached = None
                if cached is not None: return ExecutionResult(data=cached, errors=None)

        result = super().execute_graphql_request(request, data, query, variables, operation_name, show_graphiql)
        if cache_key and result and not result.errors and result.data is not None:
            try: cache.set(cache_key, result.data)
            except Exception as exc: logger.debug("Failed to store introspection cache: %s", exc)
        return result

    def get(self, request: HttpRequest, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_context(self, request):
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
        content_type = self.get_content_type(request)
        if content_type == "application/graphql": return {"query": request.body.decode()}
        if content_type == "application/json":
            try: body = request.body.decode("utf-8")
            except Exception as exc: raise HttpError(HttpResponseBadRequest(str(exc)))
            try:
                request_json = json.loads(body)
                if self.batch:
                    if isinstance(request_json, list):
                        if not request_json: raise HttpError(HttpResponseBadRequest("Received an empty list in the batch request."))
                        return request_json
                    if isinstance(request_json, dict): return request_json
                    raise HttpError(HttpResponseBadRequest("Batch requests should receive a list or object payload."))
                if isinstance(request_json, dict): return request_json
                raise HttpError(HttpResponseBadRequest("The received data is not a valid JSON query."))
            except HttpError: raise
            except (TypeError, ValueError): raise HttpError(HttpResponseBadRequest("POST body sent invalid JSON."))
        if content_type in ["application/x-www-form-urlencoded", "multipart/form-data"]: return request.POST
        return {}

    def _get_schema_name(self, request: HttpRequest) -> str:
        schema_name = getattr(self, "_schema_name", None)
        if schema_name: return schema_name
        schema_match = getattr(request, "resolver_match", None)
        if schema_match: return getattr(schema_match, "kwargs", {}).get("schema_name", "gql")
        return "gql"

    def _check_graphiql_access(self, request: HttpRequest, schema_name: str, schema_info: dict[str, Any]) -> Optional[JsonResponse]:
        if str(schema_name).lower() != "graphiql": return None
        schema_settings = _get_effective_schema_settings(schema_info)
        allowed_hosts = schema_settings.get("graphiql_allowed_hosts") or []
        if not isinstance(allowed_hosts, (list, tuple, set)): allowed_hosts = [str(allowed_hosts)]
        if not _host_allowed(request, list(allowed_hosts)): return self._schema_not_found_response(schema_name)
        if schema_settings.get("graphiql_superuser_only", False):
            if not self._check_authentication(request, schema_info):
                return JsonResponse({"errors": [{"message": "Superuser access required", "extensions": {"code": "superuser_required"}}]}, status=403)
        return None

    def _get_schema_info(self, schema_name: str) -> Optional[dict[str, Any]]:
        try:
            from ....core.registry import schema_registry
            schema_registry.discover_schemas()
            return schema_registry.get_schema(schema_name)
        except ImportError as exc:
            logger.warning("Schema registry not available"); raise SchemaRegistryUnavailable(str(exc))
        except Exception as e:
            logger.error(f"Error getting schema info for '{schema_name}': {e}")
            if isinstance(e, ImportError): raise SchemaRegistryUnavailable(str(e))
            return None

    def _get_schema_instance(self, schema_name: str, schema_info: dict[str, Any]):
        if getattr(settings, "DEBUG", False):
            try:
                from ....core.registry import schema_registry
                builder = schema_registry.get_schema_builder(schema_name)
                return builder.get_schema()
            except Exception as e:
                logger.error(f"Error getting schema instance for '{schema_name}' in DEBUG mode: {e}"); raise
        try:
            from ....core.registry import schema_registry
            return schema_registry.get_schema_instance(schema_name)
        except Exception as e:
            logger.error(f"Error getting schema instance for '{schema_name}': {e}"); raise

    def _configure_middleware(self, schema_name: str) -> None:
        try:
            from ....core.middleware import get_middleware_stack
            from ....core.registry import schema_registry
            builder = schema_registry.get_schema_builder(schema_name)
            builder_middleware = list(getattr(builder, "get_middleware", lambda: [])())
            core_middleware = get_middleware_stack(schema_name)
            self.middleware = builder_middleware + core_middleware
        except Exception as e:
            logger.warning(f"Failed to configure middleware for '{schema_name}': {e}")
            self.middleware = []

    def _configure_for_schema(self, schema_info: dict[str, Any]):
        schema_settings = _get_effective_schema_settings(schema_info)
        self.graphiql = schema_settings.get("enable_graphiql", True)
        if "pretty" in schema_settings: self.pretty = schema_settings["pretty"]
        if "batch" in schema_settings: self.batch = schema_settings["batch"]

    def check_schema_permissions(self, request: HttpRequest, schema_info: dict[str, Any]) -> bool:
        return self._check_authentication(request, schema_info)

    def _extract_query_text(self, request: HttpRequest) -> str:
        if request.method == "GET":
            query = request.GET.get("query", "")
            return str(query) if query is not None else ""
        if not request.body: return ""
        try: body = json.loads(request.body.decode("utf-8"))
        except Exception: return ""
        if isinstance(body, dict):
            query = body.get("query", "")
            return str(query) if query is not None else ""
        return ""

    def _apply_persisted_query(self, request: HttpRequest, schema_name: str) -> Optional[JsonResponse]:
        if request.method != "POST" or not request.body: return None
        content_type = request.META.get("CONTENT_TYPE", "").lower()
        if content_type and not content_type.startswith("application/json"): return None
        try: payload = json.loads(request.body.decode("utf-8"))
        except Exception: return None
        if not isinstance(payload, dict): return None
        try:
            from ....extensions.persisted_queries import resolve_persisted_query
            resolution = resolve_persisted_query(payload, schema_name=schema_name)
            if resolution.has_error():
                return JsonResponse({"errors": [{"message": resolution.error_message, "extensions": {"code": resolution.error_code}}]}, status=200)
            if resolution.query and payload.get("query") != resolution.query:
                payload["query"] = resolution.query
                request._body = json.dumps(payload).encode("utf-8")
        except Exception: pass
        return None
