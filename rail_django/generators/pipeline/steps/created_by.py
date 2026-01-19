"""
CreatedBy auto-population step.

Automatically populates the created_by field if available.
"""

from ..base import OperationFilteredStep
from ..context import MutationContext
from ..utils import auto_populate_created_by


class CreatedByStep(OperationFilteredStep):
    """
    Auto-populate created_by field if available on model.

    This step automatically sets the created_by field to the current
    user's ID if the model has this field and the user is authenticated.

    Only runs during create operations.
    """

    order = 49
    name = "created_by"
    allowed_operations = ("create",)

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Auto-populate created_by field.

        Args:
            ctx: Mutation context

        Returns:
            Context with created_by populated if applicable
        """
        ctx.input_data = auto_populate_created_by(
            ctx.input_data,
            ctx.model,
            ctx.user,
        )
        return ctx
