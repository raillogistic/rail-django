"""
Input normalization pipeline steps.

Handles enum conversion, relation operation processing, and read-only field filtering.
"""

from ..base import MutationStep
from ..context import MutationContext
from ..utils import (
    normalize_enum_inputs,
    process_relation_operations,
    filter_read_only_fields,
)


class EnumNormalizationStep(MutationStep):
    """
    Convert GraphQL enums to Django field values.

    GraphQL enums arrive as objects with a 'value' attribute.
    This step extracts the underlying values for proper Django storage.
    """

    order = 40
    name = "enum_normalization"

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Normalize enum values in input data.

        Args:
            ctx: Mutation context

        Returns:
            Context with normalized input_data
        """
        ctx.input_data = normalize_enum_inputs(ctx.input_data, ctx.model)
        return ctx


class RelationOperationProcessingStep(MutationStep):
    """
    Process relation operation inputs (connect/create/update/disconnect/set).

    Validates that relation operations follow the defined structure:
    - Singular relations (FK/O2O): Max one operation (connect, create, update)
    - List relations (M2M/Reverse): 'set' cannot be combined with others
    """

    order = 45
    name = "relation_operation_processing"

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Process relation operations with validation.

        Args:
            ctx: Mutation context

        Returns:
            Context with processed input_data or validation errors
        """
        from django.core.exceptions import ValidationError
        from ...mutations.errors import build_validation_errors

        try:
            ctx.input_data = process_relation_operations(
                ctx.input_data,
                ctx.model,
            )
        except ValidationError as e:
            ctx.add_errors(build_validation_errors(e))

        return ctx


class ReadOnlyFieldFilterStep(MutationStep):
    """
    Remove read-only fields from input.

    Fields marked as read_only in GraphQLMeta.field_config should not
    be modifiable through mutations. This step removes them from the
    input data.
    """

    order = 48
    name = "read_only_filter"

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Filter out read-only fields from input.

        Args:
            ctx: Mutation context

        Returns:
            Context with filtered input_data
        """
        ctx.input_data = filter_read_only_fields(ctx.input_data, ctx.graphql_meta)
        return ctx