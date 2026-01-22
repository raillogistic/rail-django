"""
Multitenancy extension package.
"""

from .settings import (
    MultitenancySettings,
    TenantFieldConfig,
    get_multitenancy_settings,
)
from .resolver import (
    resolve_tenant_id,
)
from .applicator import (
    apply_tenant_queryset,
    apply_tenant_to_input,
    ensure_tenant_access,
    filter_result_for_tenant,
    get_tenant_field_config,
)
from .models import (
    TenantManager,
    TenantMixin,
    TenantQuerySet,
)
from .middleware import (
    TenantContextMiddleware,
)

__all__ = [
    "MultitenancySettings",
    "TenantFieldConfig",
    "get_multitenancy_settings",
    "resolve_tenant_id",
    "apply_tenant_queryset",
    "apply_tenant_to_input",
    "ensure_tenant_access",
    "filter_result_for_tenant",
    "get_tenant_field_config",
    "TenantManager",
    "TenantMixin",
    "TenantQuerySet",
    "TenantContextMiddleware",
]
