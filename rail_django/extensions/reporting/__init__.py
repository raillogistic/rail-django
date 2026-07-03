"""
BI reporting module integrated with the GraphQL auto schema.

This extension lets us declare reusable datasets, drive rich visualizations, and
manage export jobs (PDF/CSV/JSON/XLSX) without custom resolvers. Everything is stored
as Django models so the GraphQL generator can expose CRUD plus method mutations
used by the frontend to render tables, charts, and document exports.

Key features:
    - Multiple data source support (ORM, raw SQL, Python callable)
    - Pluggable export renderers (CSV, JSON, XLSX, PDF)
    - Extensible visualization type registry
    - Reusable visualization templates with slot-based bindings
    - Scheduled materialization, exports, and conditional alerts
    - Standalone service layer for programmatic access

Usage::

    from rail_django.extensions.reporting import (
        ReportingDataset,
        ReportingVisualization,
        ReportingReport,
        ReportingExportJob,
        ReportingVisualizationTemplate,
        ReportingSchedule,
        ReportingService,
        DatasetExecutionEngine,
        ReportingError,
    )
"""

from .types import (
    ReportingError,
    ReportingExecutionContext,
    FilterSpec,
    DimensionSpec,
    MetricSpec,
    ComputedFieldSpec,
    DEFAULT_ALLOWED_LOOKUPS,
    DEFAULT_MAX_LIMIT,
    AGGREGATION_MAP,
    POSTGRES_AGGREGATIONS,
    SAFE_BUILTINS,
    SAFE_QUERY_BUILTINS,
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
    dataset_is_visible_to_user,
    report_is_visible_to_user,
    reporting_user_roles,
)

from .engine import (
    DatasetExecutionEngine,
    DatasetExecutionEngineBase,
    QueryBuilderMixin,
    AggregationMixin,
    ExecutionMixin,
    ExportMixin,
    # Data source adapters
    DataSourceAdapter,
    OrmDataSourceAdapter,
    SqlDataSourceAdapter,
    PythonDataSourceAdapter,
)

from .models import (
    ReportingDataset,
    ReportingVisualization,
    ReportingReport,
    ReportingReportBlock,
    ReportingExportJob,
    ReportingVisualizationTemplate,
    ReportingSchedule,
)

from .visualization_registry import (
    VisualizationTypeConfig,
    register_visualization_type,
    get_visualization_type,
    get_available_types,
    get_type_choices,
)

from .services import ReportingService
from .studio import ReportingStudioService
from .schema import ReportingMutation, ReportingQuery


__all__ = [
    # Models
    "ReportingDataset",
    "ReportingVisualization",
    "ReportingReport",
    "ReportingReportBlock",
    "ReportingExportJob",
    "ReportingVisualizationTemplate",
    "ReportingSchedule",
    # Engine
    "DatasetExecutionEngine",
    "DatasetExecutionEngineBase",
    "QueryBuilderMixin",
    "AggregationMixin",
    "ExecutionMixin",
    "ExportMixin",
    # Data source adapters
    "DataSourceAdapter",
    "OrmDataSourceAdapter",
    "SqlDataSourceAdapter",
    "PythonDataSourceAdapter",
    # Visualization registry
    "VisualizationTypeConfig",
    "register_visualization_type",
    "get_visualization_type",
    "get_available_types",
    "get_type_choices",
    # Service layer
    "ReportingService",
    "ReportingStudioService",
    "ReportingQuery",
    "ReportingMutation",
    # Types
    "ReportingError",
    "ReportingExecutionContext",
    "dataset_is_visible_to_user",
    "report_is_visible_to_user",
    "reporting_user_roles",
    "FilterSpec",
    "DimensionSpec",
    "MetricSpec",
    "ComputedFieldSpec",
    "SAFE_BUILTINS",
    "SAFE_QUERY_BUILTINS",
    # Constants
    "DEFAULT_ALLOWED_LOOKUPS",
    "DEFAULT_MAX_LIMIT",
    "AGGREGATION_MAP",
    "POSTGRES_AGGREGATIONS",
]
