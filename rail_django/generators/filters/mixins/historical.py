"""
Historical Model Mixin for Rail Django.

Provides special filters for django-simple-history historical models,
including instance filtering and history type filtering.
"""

from __future__ import annotations

from typing import Any, Dict, Type

import graphene
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Q


class HistoricalModelMixin:
    """
    Mixin for django-simple-history model support.

    Provides special filters for historical models including
    instance filtering and history type filtering.
    """

    def is_historical_model(self, model: Type[models.Model]) -> bool:
        """
        Check if model is from django-simple-history.

        Args:
            model: Django model class

        Returns:
            True if model is a historical model
        """
        try:
            name = getattr(model, "__name__", "")
            module = getattr(model, "__module__", "")
        except Exception:
            return False

        if name.startswith("Historical"):
            return True
        return "simple_history" in module

    def generate_historical_filters(
        self, model: Type[models.Model]
    ) -> Dict[str, graphene.InputField]:
        """
        Generate filters specific to historical models.

        Args:
            model: Historical model class

        Returns:
            Dictionary of historical filter fields
        """
        filters = {}

        # Instance filter - filter by original instance IDs
        filters["instance_in"] = graphene.InputField(
            graphene.List(graphene.NonNull(graphene.ID)),
            description="Filter by original instance IDs",
        )

        # History type filter
        try:
            history_field = model._meta.get_field("history_type")
            choices = getattr(history_field, "choices", None)
            if choices:
                filters["history_type_in"] = graphene.InputField(
                    graphene.List(graphene.NonNull(graphene.String)),
                    description="Filter by history type (create, update, delete)",
                )
        except FieldDoesNotExist:
            pass

        return filters

    def build_historical_filter_q(
        self,
        filter_name: str,
        filter_value: Any,
    ) -> Q:
        """
        Build Q object for historical model filters.

        Args:
            filter_name: Name of the historical filter
            filter_value: Filter value

        Returns:
            Django Q object
        """
        if filter_name == "instance_in" and filter_value:
            return Q(id__in=filter_value)
        elif filter_name == "history_type_in" and filter_value:
            return Q(history_type__in=filter_value)
        return Q()


__all__ = ["HistoricalModelMixin"]
