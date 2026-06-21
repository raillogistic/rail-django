"""
DatasetExecutionEngine package.

Provides the execution engine for running BI dataset queries, including
data source adapters, query building, aggregation, export, and PostgreSQL
extensions.
"""

from .base import DatasetExecutionEngineBase
from .query_builder import QueryBuilderMixin
from .aggregation import AggregationMixin
from .execution import ExecutionMixin
from .export import ExportMixin
from .core import DatasetExecutionEngine
from .postgres_engine import PostgresDatasetExecutionEngine
from .data_sources import (
    DataSourceAdapter,
    OrmDataSourceAdapter,
    SqlDataSourceAdapter,
    PythonDataSourceAdapter,
)

__all__ = [
    "DatasetExecutionEngine",
    "DatasetExecutionEngineBase",
    "QueryBuilderMixin",
    "AggregationMixin",
    "ExecutionMixin",
    "ExportMixin",
    "PostgresDatasetExecutionEngine",
    # Data source adapters
    "DataSourceAdapter",
    "OrmDataSourceAdapter",
    "SqlDataSourceAdapter",
    "PythonDataSourceAdapter",
]

