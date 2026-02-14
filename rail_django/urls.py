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
from .http.urls.health import health_urlpatterns
from .http.urls.csrf import csrf_urlpatterns
from .http.urls.audit import audit_urlpatterns
from .core.settings import get_test_graphql_endpoint_path
from .graphql.views import MultiSchemaGraphQLView, SchemaListView

_test_graphql_endpoint_path = get_test_graphql_endpoint_path().strip("/") or "graphql-test"

urlpatterns = [
    # Main GraphQL endpoint (alias for the primary schema)
    path("graphql/", MultiSchemaGraphQLView.as_view(), name="graphql"),
    # Dedicated integration testing endpoint (enabled in non-production only)
    path(
        f"{_test_graphql_endpoint_path}/",
        MultiSchemaGraphQLView.as_view(),
        {"schema_name": "gql"},
        name="graphql-test",
    ),
    path(
        f"{_test_graphql_endpoint_path}/<str:schema_name>/",
        MultiSchemaGraphQLView.as_view(),
        name="multi-schema-graphql-test",
    ),
    # Multi-schema GraphQL endpoints
    path(
        "graphql/<str:schema_name>/",
        MultiSchemaGraphQLView.as_view(),
        name="multi-schema-graphql",
    ),
    path("schemas/", SchemaListView.as_view(), name="schema-list"),
    # REST API for schema management
    path("api/v1/", include("rail_django.http.api.urls", namespace="schema_api")),
]
urlpatterns += health_urlpatterns
urlpatterns += csrf_urlpatterns
urlpatterns += audit_urlpatterns
