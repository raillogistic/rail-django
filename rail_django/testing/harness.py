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


def _normalize_headers(headers: Optional[Mapping[str, str]]) -> Dict[str, str]:
    if not headers:
        return {}
    normalized: Dict[str, str] = {}
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
    data: Optional[Dict[str, Any]] = None,
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
    settings: Optional[Dict[str, Any]] = None,
) -> SchemaHarness:
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
        variables: Optional[Dict[str, Any]] = None,
        user: Any = None,
        headers: Optional[Mapping[str, str]] = None,
        operation_name: Optional[str] = None,
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
        return self._client.execute(
            query,
            variable_values=variables,
            context_value=request,
            operation_name=operation_name,
        )


@contextmanager
def override_rail_settings(
    *,
    global_settings: Optional[Dict[str, Any]] = None,
    schema_settings: Optional[Dict[str, Any]] = None,
):
    overrides: Dict[str, Any] = {}
    if global_settings is not None:
        overrides["RAIL_DJANGO_GRAPHQL"] = global_settings
    if schema_settings is not None:
        overrides["RAIL_DJANGO_GRAPHQL_SCHEMAS"] = schema_settings
    with override_settings(**overrides):
        yield
