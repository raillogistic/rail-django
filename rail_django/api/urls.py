"""
URL patterns for GraphQL schema management REST API.
"""

from django.urls import path

from ..extensions.exporting import ExportView
from ..extensions.templating import template_urlpatterns
from .views import (
    SchemaDetailAPIView,
    SchemaDiscoveryAPIView,
    SchemaHealthAPIView,
    SchemaListAPIView,
    SchemaManagementAPIView,
    SchemaMetricsAPIView,
)

app_name = "schema_api"

urlpatterns = [
    # Schema CRUD operations
    path(
        "schemas/",
        SchemaListAPIView.as_view(),
        name="schema-list",
    ),
    path(
        "schemas/<str:schema_name>/",
        SchemaDetailAPIView.as_view(),
        name="schema-detail",
    ),
    # Schema management operations
    # path("management/", SchemaManagementAPIView.as_view(), name="schema-management"),
    # Discovery operations
    path("discovery/", SchemaDiscoveryAPIView.as_view(), name="schema-discovery"),
    # Health and monitoring
    path("health/", SchemaHealthAPIView.as_view(), name="schema-health"),
    path("metrics/", SchemaMetricsAPIView.as_view(), name="schema-metrics"),
    # Export data operations
    path("export/", ExportView.as_view(), name="model_export"),
]

urlpatterns += template_urlpatterns()
