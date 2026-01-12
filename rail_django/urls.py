"""
URL configuration for GraphQL schema registry.

This module provides URL patterns for:
- GraphQL endpoints (multi-schema)
- GraphiQL interface
- Health monitoring endpoints
- Performance monitoring
- REST API for schema management

Supports multi-schema functionality.
"""

from django.urls import include, path
from .health_urls import health_urlpatterns
from .views.graphql_views import MultiSchemaGraphQLView, SchemaListView

urlpatterns = [
    # Main GraphQL endpoint (alias for the primary schema)
    path("graphql/", MultiSchemaGraphQLView.as_view(), name="graphql"),
    # Multi-schema GraphQL endpoints
    path(
        "graphql/<str:schema_name>/",
        MultiSchemaGraphQLView.as_view(),
        name="multi-schema-graphql",
    ),
    path("schemas/", SchemaListView.as_view(), name="schema-list"),
    # REST API for schema management
    path("api/v1/", include("rail_django.api.urls", namespace="schema_api")),
]
urlpatterns += health_urlpatterns
