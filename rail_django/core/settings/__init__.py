"""
Settings package for Django GraphQL Auto-Generation.
"""

from .config import GraphQLAutoConfig
from .filtering_settings import FilteringSettings
from .mutation_settings import MutationGeneratorSettings
from .query_settings import QueryGeneratorSettings
from .schema_settings import SchemaSettings
from .type_settings import TypeGeneratorSettings

__all__ = [
    "TypeGeneratorSettings",
    "QueryGeneratorSettings",
    "FilteringSettings",
    "MutationGeneratorSettings",
    "SubscriptionGeneratorSettings",
    "SchemaSettings",
    "GraphQLAutoConfig",
]

# SubscriptionGeneratorSettings was missing from imports above but listed in __all__
from .subscription_settings import SubscriptionGeneratorSettings
