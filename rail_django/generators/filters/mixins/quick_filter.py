"""
Quick Filter Mixin for Rail Django.

Provides the ability to search across multiple text fields with a single
search term, similar to a search box in a UI.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Sequence, Type

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Q

logger = logging.getLogger(__name__)


class QuickFilterMixin:
    """
    Mixin for quick filter (multi-field search) functionality.

    Provides the ability to search across multiple text fields with a single
    search term, similar to a search box in a UI.
    """

    def _is_sensitive_field_name(self, field_name: str) -> bool:
        """Return True when a field name looks sensitive and should be excluded."""
        lowered = field_name.lower()
        return (
            "password" in lowered
            or "token" in lowered
            or "secret" in lowered
        )

    def _get_field_from_path(
        self, model: Type[models.Model], field_path: str
    ) -> Optional[models.Field]:
        """
        Get Django field from a field path (e.g., 'user__profile__name').

        Args:
            model: Starting model
            field_path: Field path with double underscores for relationships

        Returns:
            Django field instance or None if not found
        """
        try:
            current_model = model
            field_parts = field_path.split("__")

            for i, part in enumerate(field_parts):
                field = current_model._meta.get_field(part)

                if i == len(field_parts) - 1:
                    return field

                if hasattr(field, "related_model"):
                    current_model = field.related_model
                else:
                    return None

            return None
        except Exception:
            return None

    def get_default_quick_filter_fields(self, model: Type[models.Model]) -> List[str]:
        """
        Get default searchable direct primitive fields for quick filter.

        Args:
            model: Django model to get searchable fields for

        Returns:
            List of direct primitive field names suitable for quick search
        """
        searchable_fields: List[str] = []
        supported_types = (
            models.CharField,
            models.TextField,
            models.EmailField,
            models.IntegerField,
            models.FloatField,
            models.DecimalField,
            models.BooleanField,
        )

        for field in model._meta.concrete_fields:
            field_name = getattr(field, "name", None)
            if not field_name:
                continue
            if getattr(field, "is_relation", False):
                continue
            if isinstance(field, models.AutoField) or getattr(field, "primary_key", False):
                continue
            if self._is_sensitive_field_name(field_name):
                continue
            if isinstance(field, supported_types):
                searchable_fields.append(field_name)

        return searchable_fields

    def merge_quick_filter_fields(
        self,
        model: Type[models.Model],
        extra_fields: Optional[Sequence[str]] = None,
    ) -> List[str]:
        """
        Merge model default quick fields with extra configured quick fields.

        Defaults are preserved first; configured fields are appended if missing.
        """
        merged: List[str] = self.get_default_quick_filter_fields(model)
        seen = set(merged)

        for field_path in extra_fields or []:
            if not isinstance(field_path, str):
                continue
            normalized = field_path.strip()
            if not normalized or normalized in seen:
                continue
            merged.append(normalized)
            seen.add(normalized)

        return merged

    def build_quick_filter_q(
        self,
        model: Type[models.Model],
        search_value: str,
        quick_filter_fields: Optional[List[str]] = None,
    ) -> Q:
        """
        Build a Q object for quick filter search.

        Args:
            model: Django model to search
            search_value: Search term
            quick_filter_fields: Optional list of fields to search

        Returns:
            Django Q object for the search
        """
        if not search_value:
            return Q()

        if quick_filter_fields is None:
            quick_filter_fields = self.get_default_quick_filter_fields(model)

        q_objects = Q()
        for field_path in quick_filter_fields:
            try:
                field = self._get_field_from_path(model, field_path)
                if field:
                    if isinstance(
                        field, (models.CharField, models.TextField, models.EmailField)
                    ):
                        q_objects |= Q(**{f"{field_path}__icontains": search_value})
                    elif isinstance(
                        field, models.IntegerField
                    ):
                        try:
                            numeric_value = int(search_value)
                            q_objects |= Q(**{field_path: numeric_value})
                        except (ValueError, TypeError):
                            continue
                    elif isinstance(field, models.FloatField):
                        try:
                            numeric_value = float(search_value)
                            q_objects |= Q(**{field_path: numeric_value})
                        except (ValueError, TypeError):
                            continue
                    elif isinstance(field, models.DecimalField):
                        try:
                            numeric_value = Decimal(search_value)
                            q_objects |= Q(**{field_path: numeric_value})
                        except (InvalidOperation, ValueError, TypeError):
                            continue
                    elif isinstance(field, models.BooleanField):
                        if search_value.lower() in ["true", "1", "yes", "on"]:
                            q_objects |= Q(**{field_path: True})
                        elif search_value.lower() in ["false", "0", "no", "off"]:
                            q_objects |= Q(**{field_path: False})
            except (FieldDoesNotExist, AttributeError, TypeError, ValueError) as e:
                logger.debug(f"Error processing quick filter field {field_path}: {e}")
                continue

        return q_objects


__all__ = ["QuickFilterMixin"]
