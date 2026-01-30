"""
Initialization package for rail_django views.

This module makes views available for different system components.
"""

from rail_django.graphql.views import MultiSchemaGraphQLView, SchemaListView

# Make imports available at package level
from rail_django.http.views.health import (
    HealthAPIView,
    HealthDashboardView,
    HealthHistoryView,
    health_check_endpoint,
    health_components_endpoint,
    health_metrics_endpoint,
)

from rail_django.http.views.audit import (
    AuditAPIView,
    AuditDashboardView,
    AuditStatsView,
    SecurityReportView,
    AuditEventDetailView,
    AuditEventTypesView,
    get_audit_urls,
)

__all__ = [
    "HealthDashboardView",
    "HealthAPIView",
    "health_check_endpoint",
    "health_metrics_endpoint",
    "health_components_endpoint",
    "HealthHistoryView",
    "MultiSchemaGraphQLView",
    "SchemaListView",
    # Audit views
    "AuditDashboardView",
    "AuditAPIView",
    "AuditStatsView",
    "SecurityReportView",
    "AuditEventDetailView",
    "AuditEventTypesView",
    "get_audit_urls",
]
