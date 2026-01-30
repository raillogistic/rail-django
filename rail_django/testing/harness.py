"""
Testing helpers for rail-django.

This module provides small, dependency-free helpers for building schemas,
GraphQL test clients, and request contexts in unit/integration tests.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.test.utils import override_settings
from graphene.test import Client

from rail_django.core.registry import SchemaRegistry


@dataclass(frozen=True)
class SchemaHarness:
    schema: Any
    builder: Any
    registry: SchemaRegistry


def _normalize_headers(headers: Optional[Mapping[str, str]]) -> dict[str, str]:
    if not headers:
        return {}
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        if not key:
            continue
        name = key.replace("-", "_").upper()
        if name not in {"CONTENT_TYPE", "CONTENT_LENGTH"} and not name.startswith("HTTP_"):
            name = f"HTTP_{name}"
        normalized[name] = value
    return normalized


def build_request(
    path: str = "/graphql/",
    method: str = "POST",
    *,
    user: Any = None,
    headers: Optional[Mapping[str, str]] = None,
    data: Optional[dict[str, Any]] = None,
    body: Optional[str] = None,
    schema_name: str = "default",
):
    rf = RequestFactory()
    method_upper = method.upper()
    request_headers = _normalize_headers(headers)

    if method_upper in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        request = rf.get(path, data=data or {}, **request_headers)
    else:
        if body is None:
            payload = data or {}
            body = json.dumps(payload)
        request = rf.generic(
            method_upper,
            path,
            data=body,
            content_type="application/json",
            **request_headers,
        )

    request.user = user or AnonymousUser()
    request.schema_name = schema_name
    return request


def build_context(
    *,
    request: Any = None,
    user: Any = None,
    schema_name: str = "default",
    headers: Optional[Mapping[str, str]] = None,
):
    if request is None:
        request = build_request(
            schema_name=schema_name, user=user, headers=headers, data={}
        )
    if user is not None:
        request.user = user
    request.schema_name = schema_name
    return request


def build_schema(
    *,
    schema_name: str = "test",
    apps: Optional[Iterable[str]] = None,
    models: Optional[Iterable[str]] = None,
    settings: Optional[dict[str, Any]] = None,
    use_global_registry: bool = True,
) -> SchemaHarness:
    if use_global_registry:
        # Use the global registry so that FilteringSettings.from_schema()
        # can find the settings when the generator is initialized
        from rail_django.core.registry import schema_registry as global_registry

        # Clear any existing schema with this name to avoid conflicts
        if global_registry.get_schema(schema_name):
            global_registry._schemas.pop(schema_name, None)
            global_registry._schema_builders.pop(schema_name, None)
            global_registry._schema_instance_cache.pop(schema_name, None)

        # Clear filter generator and applicator singletons for this schema
        # so they get re-created with the new settings
        try:
            from rail_django.generators.filters import (
                _filter_applicator_registry,
                _filter_generator_registry,
            )
            _filter_applicator_registry.pop(schema_name, None)
            _filter_generator_registry.pop(schema_name, None)
        except ImportError:
            pass

        global_registry.register_schema(
            name=schema_name,
            apps=list(apps) if apps else None,
            models=list(models) if models else None,
            settings=settings or {},
            auto_discover=False,
        )
        builder = global_registry.get_schema_builder(schema_name)
        schema = builder.get_schema()
        return SchemaHarness(schema=schema, builder=builder, registry=global_registry)
    else:
        # Use a local isolated registry (original behavior)
        registry = SchemaRegistry()
        registry.register_schema(
            name=schema_name,
            apps=list(apps) if apps else None,
            models=list(models) if models else None,
            settings=settings or {},
            auto_discover=False,
        )
        builder = registry.get_schema_builder(schema_name)
        schema = builder.get_schema()
        return SchemaHarness(schema=schema, builder=builder, registry=registry)


class RailGraphQLTestClient:
    def __init__(
        self,
        schema: Any,
        *,
        schema_name: str = "test",
        user: Any = None,
        headers: Optional[Mapping[str, str]] = None,
    ):
        self.schema = schema
        self.schema_name = schema_name
        self.user = user
        self.headers = dict(headers or {})
        self._client = Client(schema)

    def execute(
        self,
        query: str,
        *,
        variables: Optional[dict[str, Any]] = None,
        user: Any = None,
        headers: Optional[Mapping[str, str]] = None,
        operation_name: Optional[str] = None,
        middleware: Optional[Iterable[Any]] = None,
    ):
        merged_headers = dict(self.headers)
        if headers:
            merged_headers.update(headers)

        request = build_request(
            schema_name=self.schema_name,
            user=user or self.user,
            headers=merged_headers,
            data={"query": query, "variables": variables or {}},
        )
        execute_kwargs = {
            "variable_values": variables,
            "context_value": request,
            "operation_name": operation_name,
        }
        if middleware is not None:
            execute_kwargs["middleware"] = middleware
        return self._client.execute(query, **execute_kwargs)


@contextmanager
def override_rail_schema_settings(schema_name: str, **kwargs):
    """
    Override rail settings for a specific schema at runtime.
    This modifies the _RUNTIME_SCHEMA_SETTINGS in config_proxy.
    """
    from rail_django.config_proxy import _RUNTIME_SCHEMA_SETTINGS, settings_proxy

    # Save original state
    original_exists = schema_name in _RUNTIME_SCHEMA_SETTINGS
    original_value = _RUNTIME_SCHEMA_SETTINGS.get(schema_name, {}).copy()

    # Apply overrides
    if schema_name not in _RUNTIME_SCHEMA_SETTINGS:
        _RUNTIME_SCHEMA_SETTINGS[schema_name] = {}
    _RUNTIME_SCHEMA_SETTINGS[schema_name].update(kwargs)

    # Clear cache
    settings_proxy.clear_cache()

    try:
        yield
    finally:
        # Restore original state
        if original_exists:
            _RUNTIME_SCHEMA_SETTINGS[schema_name] = original_value
        else:
            _RUNTIME_SCHEMA_SETTINGS.pop(schema_name, None)
        settings_proxy.clear_cache()


@contextmanager
def override_rail_settings(
    *,
    global_settings: Optional[dict[str, Any]] = None,
    schema_settings: Optional[dict[str, Any]] = None,
):
    from rail_django.config_proxy import _RUNTIME_SCHEMA_SETTINGS, settings_proxy

    # Save original runtime settings
    original_runtime = _RUNTIME_SCHEMA_SETTINGS.copy()

    # Clear runtime settings so they don't interfere with the overrides
    _RUNTIME_SCHEMA_SETTINGS.clear()

    overrides: dict[str, Any] = {}
    if global_settings is not None:
        overrides["RAIL_DJANGO_GRAPHQL"] = global_settings
    if schema_settings is not None:
        overrides["RAIL_DJANGO_GRAPHQL_SCHEMAS"] = schema_settings

    with override_settings(**overrides):
        settings_proxy.clear_cache()
        try:
            yield
        finally:
            # Restore runtime settings
            _RUNTIME_SCHEMA_SETTINGS.clear()
            _RUNTIME_SCHEMA_SETTINGS.update(original_runtime)
            settings_proxy.clear_cache()
