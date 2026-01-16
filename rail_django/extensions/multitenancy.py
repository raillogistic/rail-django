"""
Multi-tenancy helpers for automatic tenant scoping in GraphQL operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from django.conf import settings as django_settings
from django.db import models
from graphql import GraphQLError

from ..config_proxy import get_setting
from ..core.meta import get_model_graphql_meta

_TENANT_ID_ATTR = "_rail_tenant_id"
_TENANT_RESOLVED_ATTR = "_rail_tenant_resolved"


@dataclass(frozen=True)
class MultitenancySettings:
    enabled: bool
    isolation_mode: str
    tenant_header: str
    tenant_claim: str
    default_tenant_field: str
    allow_cross_tenant_superuser: bool
    require_tenant: bool
    tenant_subdomain: bool
    reject_mismatched_tenant_input: bool
    tenant_model: Optional[str]


@dataclass(frozen=True)
class TenantFieldConfig:
    path: str
    field: Optional[models.Field]
    is_direct: bool
    is_relation: bool


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)


def _coerce_str(value: Any, default: str) -> str:
    if value is None:
        return default
    value = str(value).strip()
    return value or default


def get_multitenancy_settings(
    schema_name: Optional[str] = None,
) -> MultitenancySettings:
    enabled = _coerce_bool(
        get_setting("multitenancy_settings.enabled", False, schema_name),
        False,
    )
    isolation_mode = _coerce_str(
        get_setting("multitenancy_settings.isolation_mode", "row", schema_name),
        "row",
    ).lower()
    tenant_header = _coerce_str(
        get_setting("multitenancy_settings.tenant_header", "X-Tenant-ID", schema_name),
        "X-Tenant-ID",
    )
    tenant_claim = _coerce_str(
        get_setting("multitenancy_settings.tenant_claim", "tenant_id", schema_name),
        "tenant_id",
    )
    default_tenant_field = _coerce_str(
        get_setting(
            "multitenancy_settings.default_tenant_field", "tenant", schema_name
        ),
        "tenant",
    )
    allow_cross_tenant_superuser = _coerce_bool(
        get_setting(
            "multitenancy_settings.allow_cross_tenant_superuser",
            True,
            schema_name,
        ),
        True,
    )
    require_tenant = _coerce_bool(
        get_setting("multitenancy_settings.require_tenant", True, schema_name),
        True,
    )
    tenant_subdomain = _coerce_bool(
        get_setting("multitenancy_settings.tenant_subdomain", False, schema_name),
        False,
    )
    reject_mismatched_tenant_input = _coerce_bool(
        get_setting(
            "multitenancy_settings.reject_mismatched_tenant_input",
            True,
            schema_name,
        ),
        True,
    )
    tenant_model = get_setting(
        "multitenancy_settings.tenant_model", None, schema_name
    )
    if tenant_model is not None:
        tenant_model = str(tenant_model).strip() or None

    if isolation_mode not in {"row", "schema"}:
        isolation_mode = "row"

    return MultitenancySettings(
        enabled=enabled,
        isolation_mode=isolation_mode,
        tenant_header=tenant_header,
        tenant_claim=tenant_claim,
        default_tenant_field=default_tenant_field,
        allow_cross_tenant_superuser=allow_cross_tenant_superuser,
        require_tenant=require_tenant,
        tenant_subdomain=tenant_subdomain,
        reject_mismatched_tenant_input=reject_mismatched_tenant_input,
        tenant_model=tenant_model,
    )


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
    if host in {"localhost", "127.0.0.1", "::1"}:
        return None
    parts = [part for part in host.split(".") if part]
    if len(parts) < 3:
        return None
    subdomain = parts[0]
    if subdomain == "www" and len(parts) > 3:
        subdomain = parts[1]
    return subdomain or None


def _get_existing_tenant_value(request: Any) -> Optional[str]:
    if request is None:
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
    if getattr(request, _TENANT_RESOLVED_ATTR, False):
        return getattr(request, _TENANT_ID_ATTR, None)

    settings = get_multitenancy_settings(schema_name)
    tenant_id = _get_existing_tenant_value(request)

    if tenant_id is None and settings.tenant_claim:
        payload = getattr(request, "jwt_payload", None)
        if isinstance(payload, dict):
            tenant_id = payload.get(settings.tenant_claim)

    if tenant_id is None and settings.tenant_header:
        tenant_id = _get_header_value(request, settings.tenant_header)

    if tenant_id is None and settings.tenant_subdomain:
        tenant_id = _extract_subdomain(request)

    setattr(request, _TENANT_RESOLVED_ATTR, True)
    setattr(request, _TENANT_ID_ATTR, tenant_id)
    if tenant_id is not None and not hasattr(request, "tenant_id"):
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


def _resolve_field_path(model: type[models.Model], path: str) -> Optional[str]:
    current_model = model
    if not path:
        return None
    parts = path.split("__")
    for idx, part in enumerate(parts):
        try:
            field = current_model._meta.get_field(part)
        except Exception:
            return None
        is_last = idx == len(parts) - 1
        if not is_last:
            if not getattr(field, "related_model", None):
                return None
            current_model = field.related_model
    return path


def get_tenant_field_config(
    model: type[models.Model], *, schema_name: Optional[str] = None
) -> Optional[TenantFieldConfig]:
    tenant_field = None
    meta_decl = getattr(model, "GraphQLMeta", None) or getattr(
        model, "GraphqlMeta", None
    )
    if meta_decl is not None and hasattr(meta_decl, "tenant_field"):
        tenant_field = getattr(meta_decl, "tenant_field", None)
        if not tenant_field:
            return None
    else:
        graphql_meta = None
        try:
            graphql_meta = get_model_graphql_meta(model)
        except Exception:
            graphql_meta = None
        if graphql_meta is not None:
            tenant_field = getattr(graphql_meta, "tenant_field", None)

    if not tenant_field:
        tenant_field = get_multitenancy_settings(schema_name).default_tenant_field

    if not tenant_field:
        return None

    tenant_field = str(tenant_field).strip()
    if not tenant_field:
        return None

    if "__" in tenant_field:
        resolved = _resolve_field_path(model, tenant_field)
        if not resolved:
            return None
        return TenantFieldConfig(
            path=resolved, field=None, is_direct=False, is_relation=False
        )

    try:
        field = model._meta.get_field(tenant_field)
    except Exception:
        return None

    is_relation = bool(getattr(field, "is_relation", False))
    return TenantFieldConfig(
        path=tenant_field, field=field, is_direct=True, is_relation=is_relation
    )


def _is_cross_tenant_allowed(
    info: Any, settings: MultitenancySettings
) -> bool:
    if not settings.allow_cross_tenant_superuser:
        return False
    user = getattr(getattr(info, "context", None), "user", None)
    return bool(user and getattr(user, "is_superuser", False))


def _strip_tenant_marker(queryset: models.QuerySet) -> models.QuerySet:
    if hasattr(queryset, "_rail_tenant_filter"):
        try:
            delattr(queryset, "_rail_tenant_filter")
        except Exception:
            try:
                setattr(queryset, "_rail_tenant_filter", None)
            except Exception:
                pass
    return queryset


def apply_tenant_queryset(
    queryset: models.QuerySet,
    info: Any,
    model: type[models.Model],
    *,
    schema_name: Optional[str] = None,
    operation: str = "read",
) -> models.QuerySet:
    settings = get_multitenancy_settings(schema_name)
    if not settings.enabled or settings.isolation_mode != "row":
        return _strip_tenant_marker(queryset)

    tenant_field = get_tenant_field_config(model, schema_name=schema_name)
    if tenant_field is None:
        return _strip_tenant_marker(queryset)

    if _is_cross_tenant_allowed(info, settings):
        return _strip_tenant_marker(queryset)

    tenant_id = resolve_tenant_id(getattr(info, "context", None), schema_name=schema_name)
    if tenant_id is None:
        if settings.require_tenant:
            raise GraphQLError("Tenant context required")
        return _strip_tenant_marker(queryset)

    filtered = queryset.filter(**{tenant_field.path: tenant_id})
    try:
        setattr(filtered, "_rail_tenant_filter", (tenant_field.path, tenant_id))
    except Exception:
        pass
    return filtered


def _get_instance_tenant_value(
    instance: models.Model, tenant_field: TenantFieldConfig
) -> Any:
    if tenant_field.is_direct and tenant_field.field is not None:
        if tenant_field.is_relation:
            field_id = f"{tenant_field.path}_id"
            if hasattr(instance, field_id):
                return getattr(instance, field_id, None)
        return getattr(instance, tenant_field.path, None)

    current: Any = instance
    for part in tenant_field.path.split("__"):
        if current is None:
            return None
        try:
            current = getattr(current, part, None)
        except Exception:
            return None

    if isinstance(current, models.Model):
        return current.pk
    return current


def ensure_tenant_access(
    instance: models.Model,
    info: Any,
    model: type[models.Model],
    *,
    schema_name: Optional[str] = None,
    operation: str = "read",
) -> None:
    settings = get_multitenancy_settings(schema_name)
    if not settings.enabled or settings.isolation_mode != "row":
        return

    tenant_field = get_tenant_field_config(model, schema_name=schema_name)
    if tenant_field is None:
        return

    if _is_cross_tenant_allowed(info, settings):
        return

    tenant_id = resolve_tenant_id(getattr(info, "context", None), schema_name=schema_name)
    if tenant_id is None:
        if settings.require_tenant:
            raise GraphQLError("Tenant context required")
        return

    instance_value = _normalize_tenant_input_value(
        _get_instance_tenant_value(instance, tenant_field)
    )
    if instance_value is None:
        raise GraphQLError("Tenant access denied")

    if str(instance_value) != str(tenant_id):
        raise GraphQLError("Tenant access denied")


def apply_tenant_to_input(
    input_data: dict[str, Any],
    info: Any,
    model: type[models.Model],
    *,
    schema_name: Optional[str] = None,
    operation: str = "create",
) -> dict[str, Any]:
    settings = get_multitenancy_settings(schema_name)
    if not settings.enabled or settings.isolation_mode != "row":
        return input_data

    tenant_field = get_tenant_field_config(model, schema_name=schema_name)
    if tenant_field is None or not tenant_field.is_direct:
        return input_data

    if _is_cross_tenant_allowed(info, settings):
        return input_data

    tenant_id = resolve_tenant_id(getattr(info, "context", None), schema_name=schema_name)
    if tenant_id is None:
        if settings.require_tenant:
            raise GraphQLError("Tenant context required")
        return input_data

    normalized_input = dict(input_data)
    incoming_value = normalized_input.get(tenant_field.path)
    if incoming_value is not None:
        incoming_value = _normalize_tenant_input_value(incoming_value)
        if str(incoming_value) != str(tenant_id):
            if settings.reject_mismatched_tenant_input:
                raise GraphQLError("Tenant mismatch in input payload")
    if operation == "update":
        normalized_input.pop(tenant_field.path, None)
        return normalized_input

    normalized_input[tenant_field.path] = tenant_id
    return normalized_input


def filter_result_for_tenant(
    result: Any, info: Any, *, schema_name: Optional[str] = None
) -> Any:
    settings = get_multitenancy_settings(schema_name)
    if not settings.enabled or settings.isolation_mode != "row":
        return result

    if isinstance(result, models.QuerySet) and hasattr(result, "model"):
        return apply_tenant_queryset(
            result, info, result.model, schema_name=schema_name
        )

    if isinstance(result, models.Model):
        ensure_tenant_access(result, info, result.__class__, schema_name=schema_name)
        return result

    if isinstance(result, (list, tuple)) and result:
        if not all(isinstance(item, models.Model) for item in result):
            return result
        model = result[0].__class__
        tenant_field = get_tenant_field_config(model, schema_name=schema_name)
        if tenant_field is None:
            return result
        if _is_cross_tenant_allowed(info, settings):
            return result
        tenant_id = resolve_tenant_id(getattr(info, "context", None), schema_name=schema_name)
        if tenant_id is None:
            if settings.require_tenant:
                raise GraphQLError("Tenant context required")
            return result
        filtered = []
        for item in result:
            value = _normalize_tenant_input_value(
                _get_instance_tenant_value(item, tenant_field)
            )
            if value is None:
                continue
            if str(value) == str(tenant_id):
                filtered.append(item)
        if isinstance(result, tuple):
            return tuple(filtered)
        return filtered

    return result


class TenantContextMiddleware:
    """
    GraphQL middleware that resolves tenant context and enforces tenant scoping.
    """

    def __init__(self, schema_name: Optional[str] = None):
        self.schema_name = schema_name

    def resolve(self, next_resolver, root, info, **kwargs):
        schema_name = self.schema_name or getattr(info.context, "schema_name", None)
        settings = get_multitenancy_settings(schema_name)
        if not settings.enabled:
            return next_resolver(root, info, **kwargs)

        resolve_tenant_id(getattr(info, "context", None), schema_name=schema_name)
        result = next_resolver(root, info, **kwargs)
        return filter_result_for_tenant(result, info, schema_name=schema_name)


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant_id: Any):
        if tenant_id in (None, ""):
            return self.none()
        return self.filter(tenant=tenant_id)


class TenantManager(models.Manager):
    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)

    def for_tenant(self, tenant_id: Any):
        return self.get_queryset().for_tenant(tenant_id)


def _resolve_tenant_model() -> str:
    settings_model = get_multitenancy_settings().tenant_model
    if settings_model:
        return settings_model
    return getattr(django_settings, "TENANT_MODEL", None) or django_settings.AUTH_USER_MODEL


class TenantMixin(models.Model):
    """
    Abstract mixin that adds a tenant foreign key and manager.
    """

    tenant = models.ForeignKey(
        _resolve_tenant_model(),
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = TenantManager()

    class GraphQLMeta:
        tenant_field = "tenant"

    class Meta:
        abstract = True
