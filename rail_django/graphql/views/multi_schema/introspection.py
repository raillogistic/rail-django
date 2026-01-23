"""
Introspection handling for MultiSchemaGraphQLView.
"""

import logging
from typing import Any, Dict

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone as django_timezone
from graphql import parse
from graphql.language.ast import FieldNode, OperationDefinitionNode

from ..utils import _get_effective_schema_settings

logger = logging.getLogger(__name__)

_INTROSPECTION_FIELDS = {"__schema", "__type", "__typename"}


class IntrospectionMixin:
    """Mixin for introspection handling and caching."""

    def _is_introspection_query(self, query: str) -> bool:
        try:
            document = parse(query)
        except Exception:
            return False

        found_operation = False
        for definition in document.definitions:
            if not isinstance(definition, OperationDefinitionNode): continue
            found_operation = True
            selections = getattr(definition.selection_set, "selections", None) or []
            if not selections: return False
            for selection in selections:
                if isinstance(selection, FieldNode):
                    if selection.name.value not in _INTROSPECTION_FIELDS: return False
                else: return False
        return found_operation

    def _should_cache_introspection(self, request: HttpRequest, query: str) -> bool:
        if getattr(settings, "DEBUG", False): return False
        if not self._is_introspection_query(query): return False

        schema_name = self._get_schema_name(request)
        if not schema_name: return False
        try:
            from ....core.security import is_introspection_allowed
            from ....core.settings import SchemaSettings
        except Exception: return False

        schema_settings = SchemaSettings.from_schema(schema_name)
        user = self._resolve_request_user(request)
        if schema_settings.authentication_required:
            if not user or not getattr(user, "is_authenticated", False): return False
        if not is_introspection_allowed(user, schema_name, enable_introspection=schema_settings.enable_introspection):
            return False
        return True

    def _get_introspection_cache_key(self, schema_name: str) -> str:
        version = "0"
        try:
            from ....core.registry import schema_registry
            builder = schema_registry.get_schema_builder(schema_name)
            version = str(builder.get_schema_version())
        except Exception: pass
        return f"rail_django:introspection:{schema_name}:{version}"

    def _allow_introspection(self, request: HttpRequest, schema_info: dict[str, Any]) -> bool:
        schema_settings = _get_effective_schema_settings(schema_info)
        enable_introspection = schema_settings.get("enable_introspection", True)
        user = getattr(request, "user", None)
        try:
            from ....core.security import is_introspection_allowed
            if is_introspection_allowed(user, getattr(schema_info, "name", None), enable_introspection=bool(enable_introspection)):
                return True
        except Exception:
            if enable_introspection: return True

        query_text = self._extract_query_text(request)
        if "__schema" in query_text or "__type" in query_text:
            self._audit_introspection_attempt(request, schema_info, query_text)
            return False
        return True

    def _audit_introspection_attempt(self, request: HttpRequest, schema_info: dict[str, Any], query_text: str) -> None:
        try:
            from ....security import security, EventType, Outcome
        except Exception: return

        user = getattr(request, "user", None)
        details = {
            "schema_name": getattr(schema_info, "name", None),
            "query_length": len(query_text or ""),
        }

        security.emit(
            EventType.QUERY_BLOCKED_INTROSPECTION,
            request=request,
            outcome=Outcome.BLOCKED,
            action="Introspection blocked",
            context=details,
            error="Introspection disabled for schema"
        )
