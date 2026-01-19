"""
Input sanitization pipeline step.

Handles escaping and cleaning of input data.
"""

from ..base import MutationStep
from ..context import MutationContext
from ..utils import sanitize_input_data


class InputSanitizationStep(MutationStep):
    """
    Sanitize input data.

    Handles:
    - Converting ID fields to strings (for UUID objects)
    - Escaping double quotes
    - Recursively processing nested structures
    """

    order = 30
    name = "sanitization"

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Sanitize input data.

        Args:
            ctx: Mutation context

        Returns:
            Context with sanitized input_data
        """
        ctx.input_data = sanitize_input_data(ctx.input_data)
        return ctx
