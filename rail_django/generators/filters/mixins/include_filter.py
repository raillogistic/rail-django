"""
Include Filter Mixin for Rail Django.

Allows including specific IDs in results regardless of other filters,
useful for ensuring selected items always appear in results.
"""

from __future__ import annotations

import logging
from typing import Any, List, Type

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Case, Q, Value, When
from django.db.models.fields import IntegerField

logger = logging.getLogger(__name__)


class IncludeFilterMixin:
    """
    Mixin for include filter (ID union) functionality.

    Allows including specific IDs in results regardless of other filters,
    useful for ensuring selected items always appear in results.
    """

    def apply_include_filter(
        self,
        queryset: models.QuerySet,
        include_ids: List[Any],
    ) -> models.QuerySet:
        """
        Apply include filter to union specified IDs into results.

        Args:
            queryset: The current filtered queryset
            include_ids: List of IDs to include

        Returns:
            Combined queryset with included IDs
        """
        if not include_ids:
            return queryset

        try:
            # Sanitize IDs
            sanitized_ids = []
            for v in include_ids:
                try:
                    if isinstance(v, str) and v.isdigit():
                        sanitized_ids.append(int(v))
                    else:
                        sanitized_ids.append(v)
                except (ValueError, TypeError):
                    sanitized_ids.append(v)

            model_cls = queryset.model

            # Build combined queryset
            combined_qs = model_cls.objects.filter(
                Q(pk__in=sanitized_ids) | Q(pk__in=queryset.values("pk"))
            ).distinct()

            # Preserve tenant filter if present
            tenant_filter = getattr(queryset, "_rail_tenant_filter", None)
            if tenant_filter:
                try:
                    tenant_path, tenant_id = tenant_filter
                    if tenant_path and tenant_id is not None:
                        combined_qs = combined_qs.filter(**{tenant_path: tenant_id})
                except (ValueError, TypeError, AttributeError):
                    pass

            # Deterministic ordering: included IDs first
            combined_qs = combined_qs.annotate(
                _include_priority=Case(
                    When(pk__in=sanitized_ids, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("_include_priority", "pk")

            return combined_qs

        except (FieldDoesNotExist, TypeError, ValueError, AttributeError) as e:
            logger.warning(f"Failed to apply include filter: {e}")
            return queryset


__all__ = ["IncludeFilterMixin"]
