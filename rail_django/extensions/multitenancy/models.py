"""
Tenant-aware models and managers.
"""

from typing import Any
from django.conf import settings as django_settings
from django.db import models
from .settings import get_multitenancy_settings


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
