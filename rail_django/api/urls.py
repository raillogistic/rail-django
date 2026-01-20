"""
URL patterns for GraphQL schema management REST API.
"""

from django.urls import path

from ..extensions.exporting import get_export_urls
from ..extensions.tasks import get_task_urls
from ..extensions.templating import template_urlpatterns
from ..extensions.excel_export import excel_urlpatterns
from .views import (
    SchemaDetailAPIView,
    SchemaDiscoveryAPIView,
    SchemaDiffAPIView,
    SchemaExportAPIView,
    SchemaHistoryAPIView,
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
    path(
        "schemas/<str:schema_name>/export/",
        SchemaExportAPIView.as_view(),
        name="schema-export",
    ),
    path(
        "schemas/<str:schema_name>/history/",
        SchemaHistoryAPIView.as_view(),
        name="schema-history",
    ),
    path(
        "schemas/<str:schema_name>/diff/",
        SchemaDiffAPIView.as_view(),
        name="schema-diff",
    ),
    # Schema management operations
    path("management/", SchemaManagementAPIView.as_view(), name="schema-management"),
    # Discovery operations
    path("discovery/", SchemaDiscoveryAPIView.as_view(), name="schema-discovery"),
    # Health and monitoring
    path("health/", SchemaHealthAPIView.as_view(), name="schema-health"),
    path("metrics/", SchemaMetricsAPIView.as_view(), name="schema-metrics"),
]

urlpatterns += get_export_urls()
urlpatterns += get_task_urls()
urlpatterns += template_urlpatterns()
urlpatterns += excel_urlpatterns()
