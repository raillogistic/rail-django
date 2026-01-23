"""
Package d'initialisation pour les vues de rail_django.

Ce module permet d'importer les vues pour différents composants du système.
"""

from rail_django.graphql.views import MultiSchemaGraphQLView, SchemaListView

# Rendre les imports disponibles au niveau du package
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
