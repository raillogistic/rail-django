"""
GraphQL Meta Configuration Package

This package provides the GraphQLMeta class and related configuration
dataclasses for declaratively configuring GraphQL behavior on Django models.

Usage:
    from rail_django.core.meta import GraphQLMeta, get_model_graphql_meta

    class MyModel(models.Model):
        name = models.CharField(max_length=100)

        class GraphqlMeta(GraphQLMeta):
            filtering = GraphQLMeta.Filtering(
                quick=["name"],
                fields={"name": GraphQLMeta.FilterField(lookups=["icontains", "eq"])}
            )
            fields = GraphQLMeta.Fields(include=["id", "name"])
"""

from .config import (
    AccessControlConfig,
    ClassificationConfig,
    FieldExposureConfig,
    FieldGuardConfig,
    FilterFieldConfig,
    FilteringConfig,
    OperationGuardConfig,
    OrderingConfig,
    PipelineConfig,
    ResolverConfig,
    RoleConfig,
)
from .graphql_meta import GraphQLMeta, get_model_graphql_meta

__all__ = [
    # Main class and factory function
    "GraphQLMeta",
    "get_model_graphql_meta",
    # Configuration dataclasses
    "FilterFieldConfig",
    "FilteringConfig",
    "FieldExposureConfig",
    "OrderingConfig",
    "ResolverConfig",
    "RoleConfig",
    "OperationGuardConfig",
    "FieldGuardConfig",
    "AccessControlConfig",
    "ClassificationConfig",
    "PipelineConfig",
]
