"""
Data source adapters for the BI reporting engine.

This package provides the abstraction layer that decouples the execution
engine from the Django ORM, enabling support for multiple source kinds
(model, raw SQL, Python callable).
"""

from .base import DataSourceAdapter
from .orm_source import OrmDataSourceAdapter
from .sql_source import SqlDataSourceAdapter
from .python_source import PythonDataSourceAdapter


__all__ = [
    "DataSourceAdapter",
    "OrmDataSourceAdapter",
    "SqlDataSourceAdapter",
    "PythonDataSourceAdapter",
]
