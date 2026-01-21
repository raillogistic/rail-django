"""
Cache utilities for query optimization.
"""

import hashlib
import json
from typing import Any, Optional, Union

from graphql import GraphQLResolveInfo


def _resolve_cache_scopes(
    scope_setting: Any,
    schema_name: Optional[str],
    extra_scopes: Optional[list[str]] = None,
) -> list[str]:
    scopes: list[str] = []
    raw_scopes: list[str] = []
    if isinstance(scope_setting, (list, tuple, set)):
        raw_scopes = [str(scope) for scope in scope_setting if scope]
    elif scope_setting:
        raw_scopes = [str(scope_setting)]

    for scope in raw_scopes:
        if scope == "schema" and schema_name:
            scopes.append(f"schema:{schema_name}")
        elif scope == "global":
            scopes.append("global")
        else:
            scopes.append(scope)

    for scope in extra_scopes or []:
        if scope:
            scopes.append(str(scope))

    if not scopes:
        scopes.append("global")
    return scopes


def _build_query_cache_key(
    info: GraphQLResolveInfo,
    *,
    schema_name: Optional[str],
    versions: list[str],
    user_id: Optional[str],
    cache_buster: Optional[str],
) -> str:
    operation = info.operation
    operation_name = None
    if operation and operation.name and operation.name.value:
        operation_name = operation.name.value

    variables = info.variable_values or {}
    query_text = str(operation) if operation is not None else ""
    query_hash = hashlib.sha256(query_text.encode("utf-8")).hexdigest()

    payload = {
        "schema": schema_name or "default",
        "field": info.field_name,
        "operation": operation_name,
        "query_hash": query_hash,
        "variables": variables,
        "user_id": user_id,
        "versions": versions,
        "cache_buster": cache_buster,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"gqlcache:{digest}"


def invalidate_query_cache(
    schema_name: Optional[str] = None, scopes: Optional[Union[str, list[str]]] = None
) -> list[str]:
    """Bump cache versions for the provided scopes to invalidate cached entries."""
    from ...core.services import get_query_cache_backend

    backend = get_query_cache_backend(schema_name)
    if backend is None:
        return []

    scope_setting: Any = scopes
    if scope_setting is None:
        scope_setting = "schema" if schema_name else "global"
    resolved_scopes = _resolve_cache_scopes(scope_setting, schema_name)
    return [backend.bump_version(scope) for scope in resolved_scopes]
