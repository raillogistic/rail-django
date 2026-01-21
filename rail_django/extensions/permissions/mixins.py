"""
Permission mixins.
"""

from typing import TYPE_CHECKING
from .base import OperationType
from .manager import permission_manager

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class PermissionFilterMixin:
    """Mixin pour filtrer les objets selon les permissions."""

    @classmethod
    def filter_queryset_by_permissions(cls, queryset, user: "AbstractUser", operation: OperationType):
        """Filtre un queryset selon les permissions de l'utilisateur."""
        if not user or not user.is_authenticated: return queryset.none()
        if user.is_superuser: return queryset
        model_name = queryset.model._meta.label_lower
        result = permission_manager.check_operation_permission(user, model_name, operation)
        if not result.allowed: return queryset.none()
        return queryset
