"""
Multitenancy GraphQL middleware.
"""

from typing import Optional
from .settings import get_multitenancy_settings
from .resolver import resolve_tenant_id
from .applicator import filter_result_for_tenant


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
