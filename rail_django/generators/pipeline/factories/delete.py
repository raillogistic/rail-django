"""
Delete mutation factory.

Generates delete mutation classes using the pipeline architecture.
"""

from typing import Any, Type

import graphene
from django.db import models

from .base import BasePipelineMutation
from ..builder import PipelineBuilder
from ...mutations.errors import MutationError


def delete_mutation_factory(
    model: Type[models.Model],
    model_type: Type[graphene.ObjectType],
    graphql_meta: Any,
    pipeline_builder: PipelineBuilder,
    tenant_applicator: Any = None,
) -> Type[graphene.Mutation]:
    """
    Factory function to create a DeleteMutation class for a model.

    Returns a concrete mutation class with explicit attributes (no closures).

    Args:
        model: Django model class
        model_type: GraphQL ObjectType for the model
        graphql_meta: GraphQLMeta configuration for the model
        pipeline_builder: PipelineBuilder instance
        tenant_applicator: Optional tenant applicator

    Returns:
        Generated DeleteMutation class
    """
    model_name = model.__name__

    # Build the pipeline
    pipeline = pipeline_builder.build_delete_pipeline(
        model,
        tenant_applicator=tenant_applicator,
    )

    # Create the mutation class
    class DeleteMutation(BasePipelineMutation):
        class Meta:
            name = f"Delete{model_name}"

        class Arguments:
            id = graphene.ID(required=True)

        object = graphene.Field(model_type)

        @classmethod
        def build_context(cls, info, input_data, instance_id=None):
            """Build context for delete operation."""
            return super().build_context(info, {}, instance_id)

        @classmethod
        def build_response(cls, ctx):
            """Build response from context."""
            if ctx.should_abort:
                return cls(ok=False, object=None, errors=ctx.errors)
            return cls(ok=True, object=ctx.result, errors=[])

    # Set class attributes after creation (avoids closure issues)
    DeleteMutation.model_class = model
    DeleteMutation.operation = "delete"
    DeleteMutation.graphql_meta = graphql_meta
    DeleteMutation.pipeline = pipeline

    # Create named class with proper name
    return type(
        f"Delete{model_name}",
        (DeleteMutation,),
        {"__doc__": f"Delete a {model_name} instance"},
    )
