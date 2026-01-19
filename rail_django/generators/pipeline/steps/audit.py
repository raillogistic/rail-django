"""
Audit pipeline step.

Handles mutation audit logging.
"""

from ..base import MutationStep
from ..context import MutationContext


class AuditStep(MutationStep):
    """
    Log mutation to audit system.

    This step runs after execution and logs the mutation details
    to the configured audit system.

    Note: Currently, audit logging is handled within the execution steps
    via the _wrap_with_audit decorator. This step is available for
    additional audit logging if needed.
    """

    order = 90  # After execution
    name = "audit"

    def should_run(self, ctx: MutationContext) -> bool:
        """
        Only audit successful operations.

        Args:
            ctx: Mutation context

        Returns:
            True if operation was successful and should be audited
        """
        return super().should_run(ctx) and ctx.result is not None

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Log mutation to audit system.

        The primary audit logging is handled in execution steps.
        This step is available for additional custom audit logging.

        Args:
            ctx: Mutation context

        Returns:
            Unchanged context
        """
        # Audit is already handled in execution steps via _wrap_with_audit
        # This step is available for additional custom audit logging
        return ctx
