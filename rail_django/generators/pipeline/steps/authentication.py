"""
Authentication pipeline step.

Verifies that the user is authenticated before proceeding with the mutation.
"""

from ..base import MutationStep
from ..context import MutationContext


class AuthenticationStep(MutationStep):
    """
    Verify user is authenticated.

    This step checks that the request has an authenticated user before
    allowing the mutation to proceed. Can be configured to allow
    unauthenticated access for specific mutations.

    Attributes:
        require_authentication: If True, anonymous users will be rejected
    """

    order = 10
    name = "authentication"

    def __init__(self, require_authentication: bool = True):
        """
        Initialize authentication step.

        Args:
            require_authentication: If True, reject unauthenticated requests
        """
        self.require_authentication = require_authentication

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Check user authentication.

        Args:
            ctx: Mutation context

        Returns:
            Context with potential authentication error
        """
        if not self.require_authentication:
            return ctx

        user = ctx.user
        if user is None or not getattr(user, "is_authenticated", False):
            ctx.add_error("Authentication required")

        return ctx
