"""
Filter Mixins Package for Rail Django.

This package provides reusable mixins for filter generation and application:

- QuickFilterMixin: Multi-field search functionality
- IncludeFilterMixin: ID union filtering for including specific records
- HistoricalModelMixin: Support for django-simple-history models
- GraphQLMetaIntegrationMixin: Integration with model's GraphQLMeta class
- SchemaSettingsMixin: Schema settings integration for exclusions

Example Usage:
    from rail_django.generators.filters.mixins import (
        QuickFilterMixin,
        IncludeFilterMixin,
        HistoricalModelMixin,
        GraphQLMetaIntegrationMixin,
        SchemaSettingsMixin,
    )

    class MyFilterGenerator(QuickFilterMixin, IncludeFilterMixin):
        def generate_filters(self, model):
            # Use quick filter functionality
            q = self.build_quick_filter_q(model, "search term")
            # ...
"""

from .quick_filter import QuickFilterMixin
from .include_filter import IncludeFilterMixin
from .historical import HistoricalModelMixin
from .graphql_meta import GraphQLMetaIntegrationMixin
from .schema_settings import SchemaSettingsMixin

__all__ = [
    "QuickFilterMixin",
    "IncludeFilterMixin",
    "HistoricalModelMixin",
    "GraphQLMetaIntegrationMixin",
    "SchemaSettingsMixin",
]
