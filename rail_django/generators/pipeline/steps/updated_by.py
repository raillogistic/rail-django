"""
UpdatedBy auto-population step.

Automatically populates the updated_by field if available.
"""

from ..base import OperationFilteredStep
from ..context import MutationContext
from ..utils import auto_populate_updated_by


class UpdatedByStep(OperationFilteredStep):
    """
    Auto-populate updated_by field if available on model.

    This step automatically sets the updated_by field to the current
    user's ID if the model has this field and the user is authenticated.

    Runs during create and update operations.
    """

    order = 50
    name = "updated_by"
    allowed_operations = ("create", "update")

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Auto-populate updated_by field.

        Args:
            ctx: Mutation context

        Returns:
            Context with updated_by populated if applicable
        """
        ctx.input_data = auto_populate_updated_by(
            ctx.input_data,
            ctx.model,
            ctx.user,
        )
        return ctx
