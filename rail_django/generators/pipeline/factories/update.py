"""
Update mutation factory.

Generates update mutation classes using the pipeline architecture.
"""

from typing import Any, Type

import graphene
from django.db import models

from .base import BasePipelineMutation
from ..builder import PipelineBuilder
from ...mutations_errors import MutationError


def update_mutation_factory(
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
    Factory function to create an UpdateMutation class for a model.

    Returns a concrete mutation class with explicit attributes (no closures).

    Args:
        model: Django model class
        model_type: GraphQL ObjectType for the model
        input_type: GraphQL InputObjectType for update input
        graphql_meta: GraphQLMeta configuration for the model
        pipeline_builder: PipelineBuilder instance
        nested_handler: Optional NestedOperationHandler
        input_validator: Optional input validator
        tenant_applicator: Optional tenant applicator

    Returns:
        Generated UpdateMutation class
    """
    model_name = model.__name__

    # Build the pipeline
    pipeline = pipeline_builder.build_update_pipeline(
        model,
        nested_handler=nested_handler,
        input_validator=input_validator,
        tenant_applicator=tenant_applicator,
    )

    # Create the mutation class
    class UpdateMutation(BasePipelineMutation):
        class Meta:
            name = f"Update{model_name}"

        class Arguments:
            id = graphene.ID(required=True)
            input = input_type(required=True)

        object = graphene.Field(model_type)

        @classmethod
        def build_context(cls, info, input_data, instance_id=None):
            """Build context, removing id from input data."""
            # Remove id from input data to avoid overwriting PK
            clean_input = {k: v for k, v in input_data.items() if k != "id"}
            return super().build_context(info, clean_input, instance_id)

        @classmethod
        def build_response(cls, ctx):
            """Build response from context."""
            if ctx.should_abort:
                return cls(ok=False, object=None, errors=ctx.errors)
            return cls(ok=True, object=ctx.result, errors=[])

    # Set class attributes after creation (avoids closure issues)
    UpdateMutation.model_class = model
    UpdateMutation.operation = "update"
    UpdateMutation.graphql_meta = graphql_meta
    UpdateMutation.pipeline = pipeline

    # Create named class with proper name
    return type(
        f"Update{model_name}",
        (UpdateMutation,),
        {"__doc__": f"Update an existing {model_name} instance"},
    )
