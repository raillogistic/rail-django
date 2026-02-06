"""
Table v3 extension package.
"""

from .schema.queries import TableQuery
from .schema.mutations import TableMutations
from .schema.subscriptions import TableSubscriptions

__all__ = ["TableQuery", "TableMutations", "TableSubscriptions"]

