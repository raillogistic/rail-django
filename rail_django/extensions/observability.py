"""
Observability hooks for GraphQL operations (Sentry/OpenTelemetry).

These hooks are optional and only active when plugins are enabled via
GRAPHQL_SCHEMA_PLUGINS.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..plugins.base import BasePlugin, ExecutionHookResult

logger = logging.getLogger(__name__)


class SentryIntegrationPlugin(BasePlugin):
    """Capture GraphQL operation errors in Sentry."""

    VERSION = "1.0.0"

    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(config)
        self._sdk = None
        if not self.enabled:
            return
        try:
            import sentry_sdk  # type: ignore

            self._sdk = sentry_sdk
        except Exception as exc:
            self.enabled = False
            logger.warning("Sentry SDK unavailable: %s", exc)

    def before_operation(self, schema_name, operation_type, operation_name, info, context):
        if not self._sdk:
            return ExecutionHookResult()
        try:
            scope = self._sdk.Hub.current.scope
            scope.set_tag("graphql.schema", schema_name)
            scope.set_tag("graphql.operation_type", operation_type)
            if operation_name:
                scope.set_tag("graphql.operation_name", operation_name)
        except Exception:
            pass
        return ExecutionHookResult()

    def after_operation(self, schema_name, operation_type, operation_name, info, result, error, context):
        if not self._sdk:
            return ExecutionHookResult()
        if error is not None:
            try:
                self._sdk.capture_exception(error)
            except Exception:
                pass
        return ExecutionHookResult()


class OpenTelemetryIntegrationPlugin(BasePlugin):
    """Create basic OpenTelemetry spans for GraphQL operations."""

    VERSION = "1.0.0"

    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(config)
        self._tracer = None
        if not self.enabled:
            return
        try:
            from opentelemetry import trace  # type: ignore

            self._tracer = trace.get_tracer("rail_django.graphql")
        except Exception as exc:
            self.enabled = False
            logger.warning("OpenTelemetry unavailable: %s", exc)

    def before_operation(self, schema_name, operation_type, operation_name, info, context):
        if not self._tracer:
            return ExecutionHookResult()
        try:
            span_name = operation_name or info.field_name or "graphql"
            span = self._tracer.start_span(span_name)
            span.set_attribute("graphql.schema", schema_name)
            span.set_attribute("graphql.operation_type", operation_type)
            if operation_name:
                span.set_attribute("graphql.operation_name", operation_name)
            context["otel_span"] = span
        except Exception:
            pass
        return ExecutionHookResult()

    def after_operation(self, schema_name, operation_type, operation_name, info, result, error, context):
        span = context.get("otel_span")
        if not span:
            return ExecutionHookResult()
        try:
            if error is not None:
                span.record_exception(error)
            span.end()
        except Exception:
            pass
        return ExecutionHookResult()
