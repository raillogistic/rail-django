"""
GraphQL Meta Integration Mixin for Rail Django.

Reads filter configuration from model's GraphQLMeta class to
customize filter generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from django.db import models


class GraphQLMetaIntegrationMixin:
    """
    Mixin for GraphQLMeta integration.

    Reads filter configuration from model's GraphQLMeta class to
    customize filter generation.
    """

    def get_graphql_meta(self, model: Type[models.Model]) -> Optional[Any]:
        """
        Get GraphQLMeta for a model.

        Args:
            model: Django model class

        Returns:
            GraphQLMeta object or None
        """
        try:
            from rail_django.core.meta import get_model_graphql_meta

            return get_model_graphql_meta(model)
        except ImportError:
            return None

    def apply_field_config_overrides(
        self,
        field_name: str,
        model: Type[models.Model],
    ) -> Optional[Dict[str, Any]]:
        """
        Get field-specific filter configuration from GraphQLMeta.

        Args:
            field_name: Name of the field
            model: Django model class

        Returns:
            Field configuration dictionary or None
        """
        graphql_meta = self.get_graphql_meta(model)
        if not graphql_meta:
            return None

        try:
            field_config = graphql_meta.filtering.fields.get(field_name)
            return field_config
        except AttributeError:
            return None

    def get_custom_filters(self, model: Type[models.Model]) -> Dict[str, Any]:
        """
        Get custom filters defined in GraphQLMeta.

        Args:
            model: Django model class

        Returns:
            Dictionary of custom filter definitions
        """
        graphql_meta = self.get_graphql_meta(model)
        if not graphql_meta:
            return {}

        try:
            if graphql_meta.custom_filters:
                return graphql_meta.get_custom_filters()
        except AttributeError:
            pass

        return {}

    def get_quick_filter_fields(self, model: Type[models.Model]) -> List[str]:
        """
        Get quick filter fields from GraphQLMeta or auto-detect.

        Args:
            model: Django model class

        Returns:
            List of field names for quick filter
        """
        graphql_meta = self.get_graphql_meta(model)
        if graphql_meta:
            try:
                quick_fields = list(getattr(graphql_meta, "quick_filter_fields", []))
                if quick_fields:
                    return quick_fields
            except (TypeError, AttributeError):
                pass

        # Fall back to auto-detection
        from .quick_filter import QuickFilterMixin

        return QuickFilterMixin().get_default_quick_filter_fields(model)


__all__ = ["GraphQLMetaIntegrationMixin"]
