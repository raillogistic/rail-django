"""
Tenant resolution logic.
"""

from typing import Any, Optional
from django.db import models
from .settings import get_multitenancy_settings

_TENANT_ID_ATTR = "_rail_tenant_id"
_TENANT_RESOLVED_ATTR = "_rail_tenant_resolved"
_TENANT_CACHE_ATTR = "_rail_tenant_cache"


def _normalize_header_key(header_name: str) -> str:
    name = header_name.upper().replace("-", "_")
    if name not in {"CONTENT_TYPE", "CONTENT_LENGTH"} and not name.startswith("HTTP_"):
        name = f"HTTP_{name}"
    return name


def _get_header_value(request: Any, header_name: str) -> Optional[str]:
    if not header_name:
        return None
    try:
        headers = getattr(request, "headers", None)
        if headers:
            value = headers.get(header_name)
            if value:
                return str(value).strip() or None
    except Exception:
        pass
    meta = getattr(request, "META", None)
    if isinstance(meta, dict):
        key = _normalize_header_key(header_name)
        value = meta.get(key)
        if value:
            return str(value).strip() or None
    return None


def _extract_subdomain(request: Any) -> Optional[str]:
    host = ""
    try:
        host = request.get_host()
    except Exception:
        host = ""
    if not host:
        meta = getattr(request, "META", None)
        if isinstance(meta, dict):
            host = meta.get("HTTP_HOST", "") or meta.get("SERVER_NAME", "")
    host = str(host or "").strip().lower()
    if not host:
        return None
    host = host.split(":", 1)[0]
    Partials = [part for part in host.split(".") if part]
    if len(Partials) < 3:
        return None
    subdomain = Partials[0]
    if subdomain == "www" and len(Partials) > 3:
        subdomain = Partials[1]
    return subdomain or None


def _get_existing_tenant_value(
    request: Any, *, schema_name: Optional[str] = None
) -> Optional[str]:
    if request is None:
        return None
    if schema_name:
        request_schema = getattr(request, "schema_name", None)
        if request_schema and request_schema != schema_name:
            return None
    existing = getattr(request, "tenant_id", None)
    if existing not in (None, ""):
        return existing
    existing = getattr(request, "tenant", None)
    if existing not in (None, ""):
        if isinstance(existing, models.Model):
            return existing.pk
        return existing
    return None


def resolve_tenant_id(
    request: Any, *, schema_name: Optional[str] = None
) -> Optional[str]:
    if request is None:
        return None
    cache = getattr(request, _TENANT_CACHE_ATTR, None)
    if not isinstance(cache, dict):
        cache = {}
        try:
            setattr(request, _TENANT_CACHE_ATTR, cache)
        except Exception:
            cache = {}

    cache_key = schema_name or "default"
    if cache_key in cache:
        return cache[cache_key]

    settings = get_multitenancy_settings(schema_name)
    tenant_id = _get_existing_tenant_value(request, schema_name=schema_name)

    if tenant_id is None and settings.tenant_claim:
        payload = getattr(request, "jwt_payload", None)
        if isinstance(payload, dict):
            tenant_id = payload.get(settings.tenant_claim)

    if tenant_id is None and settings.tenant_header:
        tenant_id = _get_header_value(request, settings.tenant_header)

    if tenant_id is None and settings.tenant_subdomain:
        tenant_id = _extract_subdomain(request)

    cache[cache_key] = tenant_id
    if cache_key == "default":
        setattr(request, _TENANT_RESOLVED_ATTR, True)
        setattr(request, _TENANT_ID_ATTR, tenant_id)
    if tenant_id is not None and not hasattr(request, "tenant_id"):
        request_schema = getattr(request, "schema_name", None)
        if request_schema in (None, schema_name, cache_key):
            setattr(request, "tenant_id", tenant_id)
    return tenant_id


def _normalize_tenant_input_value(value: Any) -> Any:
    if isinstance(value, models.Model):
        return value.pk
    if isinstance(value, (list, tuple)):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        try:
            from graphql_relay import from_global_id

            _, decoded = from_global_id(value)
            if decoded:
                return decoded
        except Exception:
            return value
    return value
