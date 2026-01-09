"""
URL configuration for GraphQL schema registry.

This module provides URL patterns for:
- GraphQL endpoints (single and multi-schema)
- GraphQL Playground and GraphiQL interfaces
- Health monitoring endpoints
- Performance monitoring
- REST API for schema management

Supports both backward compatibility with single schema
and new multi-schema functionality.
"""

from django.urls import include, path
from .schema import schema as _default_schema  # ensure default schema registry init
from .views.graphql_views import (
    GraphQLPlaygroundView,
    MultiSchemaGraphQLView,
    SchemaListView,
)

urlpatterns = [
    # Main GraphQL endpoint (backward compatibility)
    path("graphql/", MultiSchemaGraphQLView.as_view(), name="graphql"),
    # Multi-schema GraphQL endpoints
    path(
        "graphql/<str:schema_name>/",
        MultiSchemaGraphQLView.as_view(),
        name="multi-schema-graphql",
    ),
    path("schemas/", SchemaListView.as_view(), name="schema-list"),
    path(
        "playground/<str:schema_name>/",
        GraphQLPlaygroundView.as_view(),
        name="schema-playground",
    ),
    # REST API for schema management
    path("api/v1/", include("rail_django.api.urls", namespace="schema_api")),
]
