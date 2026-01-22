"""
Multitenancy settings and configurations.
"""

from dataclasses import dataclass
from typing import Any, Optional
from django.db import models
from ...config_proxy import get_setting


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
