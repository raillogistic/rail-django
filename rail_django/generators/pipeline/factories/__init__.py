"""
Mutation factories for creating GraphQL mutation classes.

These factories generate concrete mutation classes using the pipeline
architecture, eliminating the closure-based generation from the original
implementation.
"""

from .base import BasePipelineMutation
from .create import create_mutation_factory
from .update import update_mutation_factory
from .delete import delete_mutation_factory

__all__ = [
    "BasePipelineMutation",
    "create_mutation_factory",
    "update_mutation_factory",
    "delete_mutation_factory",
]
