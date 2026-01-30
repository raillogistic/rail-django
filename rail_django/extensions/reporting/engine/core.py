"""
DatasetExecutionEngine core class.
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
    """

    def __init__(self, dataset: "ReportingDataset"):
        super().__init__(dataset)
