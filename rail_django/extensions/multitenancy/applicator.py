"""
Tenant application logic for querysets and inputs.
"""

from typing import Any, List, Optional, Type
from django.db import models
from graphql import GraphQLError

from ...core.meta import get_model_graphql_meta
from .settings import MultitenancySettings, TenantFieldConfig, get_multitenancy_settings
from .resolver import resolve_tenant_id, _normalize_tenant_input_value


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
    print(f"DEBUG: tenant_field={tenant_field}")
    if tenant_field is None:
        return _strip_tenant_marker(queryset)

    if _is_cross_tenant_allowed(info, settings):
        print(f"DEBUG: cross tenant allowed")
        return _strip_tenant_marker(queryset)

    tenant_id = resolve_tenant_id(getattr(info, "context", None), schema_name=schema_name)
    print(f"DEBUG: tenant_id={tenant_id}")
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
