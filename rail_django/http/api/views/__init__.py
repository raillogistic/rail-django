"""
REST API views for GraphQL schema management.
"""

from .base import BaseAPIView
from .schema_detail import SchemaDetailAPIView
from .schema_list import SchemaListAPIView
from .protected_media import ProtectedMediaAPIView
from .schema_management import (
    SchemaDiscoveryAPIView,
    SchemaHealthAPIView,
    SchemaManagementAPIView,
    SchemaMetricsAPIView,
)
from .schema_ops import SchemaDiffAPIView, SchemaExportAPIView, SchemaHistoryAPIView

__all__ = [
    "BaseAPIView",
    "SchemaListAPIView",
    "SchemaDetailAPIView",
    "SchemaManagementAPIView",
    "SchemaDiscoveryAPIView",
    "SchemaHealthAPIView",
    "SchemaMetricsAPIView",
    "ProtectedMediaAPIView",
    "SchemaExportAPIView",
    "SchemaHistoryAPIView",
    "SchemaDiffAPIView",
]
