"""
DatasetExecutionEngine package.

This module provides the DatasetExecutionEngine class that executes
ReportingDataset definitions against their underlying models.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import DatasetExecutionEngineBase
from .query_builder import QueryBuilderMixin
from .aggregation import AggregationMixin
from .execution import ExecutionMixin
from .export import ExportMixin

if TYPE_CHECKING:
    from ..models.dataset import ReportingDataset


class DatasetExecutionEngine(
    ExportMixin,
    ExecutionMixin,
    AggregationMixin,
    QueryBuilderMixin,
    DatasetExecutionEngineBase,
):
    """
    Executes a ReportingDataset definition against its underlying model.

    The engine converts JSON definitions (dimensions, metrics, filters, computed
    fields) into QuerySets and serializable payloads used by GraphQL mutations.

    This class combines functionality from multiple mixins:
    - DatasetExecutionEngineBase: Core initialization and utility methods
    - QueryBuilderMixin: Query building and filter compilation
    - AggregationMixin: Resolution methods and basic run() operation
    - ExecutionMixin: Dynamic run_query() and describe_dataset methods
    - ExportMixin: Pivot and export functionality
    """

    def __init__(self, dataset: "ReportingDataset"):
        super().__init__(dataset)


__all__ = [
    "DatasetExecutionEngine",
    "DatasetExecutionEngineBase",
    "QueryBuilderMixin",
    "AggregationMixin",
    "ExecutionMixin",
    "ExportMixin",
]
