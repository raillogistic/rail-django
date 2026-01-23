"""
GraphQL views package for Rail Django.

This package provides multi-schema GraphQL views with support for:
- Dynamic schema selection based on URL parameters
- Per-schema authentication requirements
- Schema-specific GraphiQL configuration
- Custom error handling per schema
- Schema listing and metadata

Classes:
    MultiSchemaGraphQLView: Main GraphQL view supporting multiple schemas.
    SchemaListView: View for listing available schemas.

Usage:
    from rail_django.graphql.views import MultiSchemaGraphQLView, SchemaListView

    urlpatterns = [
        path(
            'graphql/<str:schema_name>/',
            MultiSchemaGraphQLView.as_view(),
            name='graphql'
        ),
        path('schemas/', SchemaListView.as_view(), name='schema-list'),
    ]
"""

from .multi_schema import MultiSchemaGraphQLView
from .schema_list import SchemaListView

__all__ = [
    "MultiSchemaGraphQLView",
    "SchemaListView",
]
