"""
Validation pipeline steps.

Handles input validation and nested operation limit checking.
"""

from typing import Any, Optional

from ..base import MutationStep
from ..context import MutationContext


class InputValidationStep(MutationStep):
    """
    Run input validator on mutation data.

    Uses the configured input validator to validate and sanitize
    the mutation input according to defined rules.
    """

    order = 60
    name = "input_validation"

    def __init__(self, input_validator: Optional[Any] = None):
        """
        Initialize validation step.

        Args:
            input_validator: Optional input validator instance
        """
        self.input_validator = input_validator

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Validate and sanitize input data.

        Args:
            ctx: Mutation context

        Returns:
            Context with validated input_data
        """
        if self.input_validator is None:
            return ctx

        ctx.input_data = self.input_validator.validate_and_sanitize(
            ctx.model.__name__,
            ctx.input_data,
        )
        return ctx


class NestedLimitValidationStep(MutationStep):
    """
    Validate nested operation limits.

    Checks that the input doesn't exceed configured limits for:
    - Maximum nesting depth
    - Maximum items per list
    - Maximum total nodes
    """

    order = 65
    name = "nested_limit_validation"

    def __init__(self, nested_handler: Optional[Any] = None):
        """
        Initialize nested limit validation step.

        Args:
            nested_handler: Optional NestedOperationHandler instance
        """
        self.nested_handler = nested_handler

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Validate input against nested operation limits.

        Args:
            ctx: Mutation context

        Returns:
            Context with potential limit errors
        """
        if self.nested_handler is None:
            return ctx

        from ...mutations.limits import (
            _get_nested_validation_limits,
            _validate_nested_limits,
        )

        limits = _get_nested_validation_limits(ctx.info, self.nested_handler)
        errors = _validate_nested_limits(ctx.input_data, limits)

        if errors:
            ctx.add_errors(errors)

        return ctx


class NestedDataValidationStep(MutationStep):
    """
    Validate nested data structure before processing.

    Uses the nested operation handler to validate the structure
    of nested create/update operations.
    """

    order = 70
    name = "nested_data_validation"

    def __init__(self, nested_handler: Optional[Any] = None):
        """
        Initialize nested data validation step.

        Args:
            nested_handler: Optional NestedOperationHandler instance
        """
        self.nested_handler = nested_handler

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Validate nested data structure.

        Args:
            ctx: Mutation context

        Returns:
            Context with potential validation errors
        """
        if self.nested_handler is None:
            return ctx

        from ...mutations.errors import build_error_list

        validation_errors = self.nested_handler.validate_nested_data(
            ctx.model,
            ctx.input_data,
            ctx.operation,
        )

        if validation_errors:
            ctx.add_errors(build_error_list(validation_errors))

        return ctx
