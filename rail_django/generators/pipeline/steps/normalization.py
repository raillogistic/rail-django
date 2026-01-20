"""
Input normalization pipeline steps.

Handles enum conversion, dual field processing, and read-only field filtering.
"""

from ..base import MutationStep
from ..context import MutationContext
from ..utils import (
    normalize_enum_inputs,
    process_dual_fields,
    filter_read_only_fields,
    get_mandatory_fields,
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


class DualFieldProcessingStep(MutationStep):
    """
    Process nested_X vs X field priority.

    Handles the dual field pattern where users can provide either:
    - A direct ID reference (field_name: "123")
    - A nested object to create (nested_field_name: {data})

    Validates mutual exclusivity and transforms nested fields
    to direct fields for downstream processing.
    """

    order = 45
    name = "dual_field_processing"

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Process dual fields with validation.

        Args:
            ctx: Mutation context

        Returns:
            Context with processed input_data or validation errors
        """
        from django.core.exceptions import ValidationError
        from ...mutations_errors import build_validation_errors

        try:
            # Only enforce mandatory fields for create operations
            # Update operations should not require mandatory fields
            mandatory = None
            if ctx.operation == "create":
                mandatory = get_mandatory_fields(ctx.model, ctx.graphql_meta)

            ctx.input_data = process_dual_fields(
                ctx.input_data,
                ctx.model,
                mandatory_fields=mandatory,
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
