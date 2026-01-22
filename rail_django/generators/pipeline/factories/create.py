"""
Create mutation factory.

Generates create mutation classes using the pipeline architecture.
"""

from typing import Any, Type

import graphene
from django.db import models

from .base import BasePipelineMutation
from ..builder import PipelineBuilder
from ...mutations.errors import MutationError


def create_mutation_factory(
    model: Type[models.Model],
    model_type: Type[graphene.ObjectType],
    input_type: Type[graphene.InputObjectType],
    graphql_meta: Any,
    pipeline_builder: PipelineBuilder,
    nested_handler: Any = None,
    input_validator: Any = None,
    tenant_applicator: Any = None,
) -> Type[graphene.Mutation]:
    """
    Factory function to create a CreateMutation class for a model.

    Returns a concrete mutation class with explicit attributes (no closures).

    Args:
        model: Django model class
        model_type: GraphQL ObjectType for the model
        input_type: GraphQL InputObjectType for create input
        graphql_meta: GraphQLMeta configuration for the model
        pipeline_builder: PipelineBuilder instance
        nested_handler: Optional NestedOperationHandler
        input_validator: Optional input validator
        tenant_applicator: Optional tenant applicator

    Returns:
        Generated CreateMutation class
    """
    model_name = model.__name__

    # Build the pipeline
    pipeline = pipeline_builder.build_create_pipeline(
        model,
        nested_handler=nested_handler,
        input_validator=input_validator,
        tenant_applicator=tenant_applicator,
    )

    # Create the mutation class
    class CreateMutation(BasePipelineMutation):
        class Meta:
            name = f"Create{model_name}"

        class Arguments:
            input = input_type(required=True)

        object = graphene.Field(model_type)

        @classmethod
        def build_response(cls, ctx):
            """Build response from context."""
            if ctx.should_abort:
                return cls(ok=False, object=None, errors=ctx.errors)
            return cls(ok=True, object=ctx.result, errors=None)

    # Set class attributes after creation (avoids closure issues)
    CreateMutation.model_class = model
    CreateMutation.operation = "create"
    CreateMutation.graphql_meta = graphql_meta
    CreateMutation.pipeline = pipeline

    # Create named class with proper name
    return type(
        f"Create{model_name}",
        (CreateMutation,),
        {"__doc__": f"Create a new {model_name} instance"},
    )
