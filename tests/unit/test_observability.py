"""
Unit tests for observability plugins.
"""

import sys
import types

import pytest

from rail_django.extensions.observability import (
    OpenTelemetryIntegrationPlugin,
    SentryIntegrationPlugin,
)

pytestmark = pytest.mark.unit


def test_sentry_plugin_sets_tags_and_captures_exception():
    captured = []

    class _Scope:
        def __init__(self):
            self.tags = {}

        def set_tag(self, key, value):
            self.tags[key] = value

    scope = _Scope()
    hub = types.SimpleNamespace(current=types.SimpleNamespace(scope=scope))

    dummy = types.SimpleNamespace(
        Hub=hub,
        capture_exception=lambda exc: captured.append(exc),
    )

    class _SentryPlugin(SentryIntegrationPlugin):
        def get_name(self):
            return "SentryIntegrationPlugin"

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "sentry_sdk", dummy)
        plugin = _SentryPlugin({"enabled": True})
        context = {}

        plugin.before_operation("default", "query", "Ping", None, context)
        plugin.after_operation("default", "query", "Ping", None, None, ValueError("boom"), context)

    assert scope.tags["graphql.schema"] == "default"
    assert scope.tags["graphql.operation_type"] == "query"
    assert scope.tags["graphql.operation_name"] == "Ping"
    assert captured


def test_opentelemetry_plugin_records_span():
    spans = []

    class _Span:
        def __init__(self, name):
            self.name = name
            self.attributes = {}
            self.ended = False
            self.exceptions = []

        def set_attribute(self, key, value):
            self.attributes[key] = value

        def record_exception(self, exc):
            self.exceptions.append(exc)

        def end(self):
            self.ended = True

    class _Tracer:
        def start_span(self, name):
            span = _Span(name)
            spans.append(span)
            return span

    trace_module = types.SimpleNamespace(get_tracer=lambda name: _Tracer())
    otel_module = types.SimpleNamespace(trace=trace_module)

    class _OpenTelemetryPlugin(OpenTelemetryIntegrationPlugin):
        def get_name(self):
            return "OpenTelemetryIntegrationPlugin"

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "opentelemetry", otel_module)
        mp.setitem(sys.modules, "opentelemetry.trace", trace_module)
        plugin = _OpenTelemetryPlugin({"enabled": True})
        context = {}

        plugin.before_operation("default", "query", "Ping", types.SimpleNamespace(field_name="ping"), context)
        plugin.after_operation("default", "query", "Ping", None, None, RuntimeError("fail"), context)

    assert spans
    assert spans[0].ended is True
    assert spans[0].exceptions

