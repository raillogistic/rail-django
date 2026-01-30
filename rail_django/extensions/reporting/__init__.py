"""
BI reporting module integrated with the GraphQL auto schema.

This extension lets us declare reusable datasets, drive rich visualizations, and
manage export jobs (PDF/CSV/JSON) without custom resolvers. Everything is stored
as Django models so the GraphQL generator can expose CRUD plus method mutations
used by the frontend to render tables, charts, and document exports.

Usage:
    from rail_django.extensions.reporting import (
        ReportingDataset,
        ReportingVisualization,
        ReportingReport,
        ReportingReportBlock,
        ReportingExportJob,
        DatasetExecutionEngine,
        ReportingError,
    )
"""

from .types import (
    ReportingError,
    FilterSpec,
    DimensionSpec,
    MetricSpec,
    ComputedFieldSpec,
    DEFAULT_ALLOWED_LOOKUPS,
    DEFAULT_MAX_LIMIT,
    AGGREGATION_MAP,
    POSTGRES_AGGREGATIONS,
)

from .utils import (
    _safe_query_expression,
    _safe_formula_eval,
    _to_filter_list,
    _to_ordering,
    _coerce_int,
    _stable_json_dumps,
    _hash_query_payload,
    _safe_identifier,
    _combine_q,
    _json_sanitize,
)

from .security import (
    _reporting_roles,
    _reporting_operations,
)

from .engine import (
    DatasetExecutionEngine,
    DatasetExecutionEngineBase,
    QueryBuilderMixin,
    AggregationMixin,
    ExecutionMixin,
    ExportMixin,
)

from .models import (
    ReportingDataset,
    ReportingVisualization,
    ReportingReport,
    ReportingReportBlock,
    ReportingExportJob,
)


__all__ = [
    # Models
    "ReportingDataset",
    "ReportingVisualization",
    "ReportingReport",
    "ReportingReportBlock",
    "ReportingExportJob",
    # Engine
    "DatasetExecutionEngine",
    "DatasetExecutionEngineBase",
    "QueryBuilderMixin",
    "AggregationMixin",
    "ExecutionMixin",
    "ExportMixin",
    # Types
    "ReportingError",
    "FilterSpec",
    "DimensionSpec",
    "MetricSpec",
    "ComputedFieldSpec",
    # Constants
    "DEFAULT_ALLOWED_LOOKUPS",
    "DEFAULT_MAX_LIMIT",
    "AGGREGATION_MAP",
    "POSTGRES_AGGREGATIONS",
]
