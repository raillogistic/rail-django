"""
Base mutation class for pipeline architecture.

Provides common functionality for all pipeline-based mutations.
"""

from typing import Any, Optional, Type

import graphene
from django.db import models, transaction

from ..context import MutationContext
from ..base import MutationPipeline
from ...mutations_errors import (
    MutationError,
    build_validation_errors,
    build_integrity_errors,
    build_graphql_auto_errors,
    build_mutation_error,
)


class BasePipelineMutation(graphene.Mutation):
    """
    Base mutation class using pipeline architecture.

    Subclasses must define:
    - model_class: The Django model
    - pipeline: The MutationPipeline to execute
    - operation: "create", "update", or "delete"

    This class provides:
    - Standard return fields (ok, errors)
    - Context building
    - Pipeline execution with error handling
    - Transaction management

    Example:
        class CreateBook(BasePipelineMutation):
            model_class = Book
            pipeline = create_pipeline
            operation = "create"

            class Arguments:
                input = BookInput(required=True)

            object = graphene.Field(BookType)
    """

    # Class attributes set by factory
    model_class: Type[models.Model] = None
    pipeline: MutationPipeline = None
    operation: str = None
    graphql_meta: Any = None

    # Standard return fields
    ok = graphene.Boolean()
    errors = graphene.List(MutationError)

    @classmethod
    def build_context(
        cls,
        info: graphene.ResolveInfo,
        input_data: dict[str, Any],
        instance_id: Optional[str] = None,
    ) -> MutationContext:
        """
        Build initial mutation context.

        Args:
            info: GraphQL resolve info
            input_data: Input data from mutation arguments
            instance_id: Optional ID for update/delete operations

        Returns:
            Initialized MutationContext
        """
        return MutationContext(
            info=info,
            model=cls.model_class,
            operation=cls.operation,
            raw_input=input_data.copy(),
            input_data=input_data.copy(),
            instance_id=instance_id,
            graphql_meta=cls.graphql_meta,
        )

    @classmethod
    def execute_pipeline(cls, ctx: MutationContext) -> MutationContext:
        """
        Execute the mutation pipeline.

        Args:
            ctx: Mutation context

        Returns:
            Processed mutation context
        """
        return cls.pipeline.execute(ctx)

    @classmethod
    def build_response(cls, ctx: MutationContext):
        """
        Build mutation response from context.

        Override in subclasses for custom response building.

        Args:
            ctx: Processed mutation context

        Returns:
            Mutation instance with response data
        """
        raise NotImplementedError("Subclasses must implement build_response")

    @classmethod
    @transaction.atomic
    def mutate(cls, root, info, **kwargs):
        """
        Standard mutation entry point.

        Handles context building, pipeline execution, and error handling.

        Args:
            root: GraphQL root value
            info: GraphQL resolve info
            **kwargs: Mutation arguments

        Returns:
            Mutation instance with response data
        """
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError
        from rail_django.core.exceptions import GraphQLAutoError

        try:
            # Build context from arguments
            input_data = kwargs.get("input", {})
            instance_id = kwargs.get("id")

            ctx = cls.build_context(info, input_data, instance_id)

            # Execute pipeline
            ctx = cls.execute_pipeline(ctx)

            # Build response
            return cls.build_response(ctx)

        except ValidationError as exc:
            return cls(ok=False, errors=build_validation_errors(exc))

        except GraphQLAutoError as exc:
            return cls(ok=False, errors=build_graphql_auto_errors(exc))

        except IntegrityError as exc:
            transaction.set_rollback(True)
            return cls(ok=False, errors=build_integrity_errors(cls.model_class, exc))

        except Exception as exc:
            transaction.set_rollback(True)
            return cls(
                ok=False,
                errors=[build_mutation_error(message=str(exc))],
            )
