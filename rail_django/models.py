"""
Model registry for rail_django extensions.

This module imports reporting models so Django auto-discovery registers them and
the GraphQL auto schema can expose CRUD and method-based mutations.
"""

from rail_django.extensions.reporting import (
    ReportingDataset,
    ReportingExportJob,
    ReportingReport,
    ReportingReportBlock,
    ReportingVisualization,
)
from rail_django.extensions.audit import AuditEventModel

__all__ = [
    "AuditEventModel",
    "ReportingDataset",
    "ReportingVisualization",
    "ReportingReport",
    "ReportingReportBlock",
    "ReportingExportJob",
]
