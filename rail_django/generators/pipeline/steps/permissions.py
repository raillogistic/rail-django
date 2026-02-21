"""
Permission pipeline steps.

Checks Django model permissions and GraphQLMeta operation guards.
"""

from ..base import MutationStep
from ..context import MutationContext


class ModelPermissionStep(MutationStep):
    """
    Check Django model permissions (add, change, delete).

    This step verifies that the user has the appropriate Django permission
    for the mutation operation:
    - create -> add_<model>
    - update -> change_<model>
    - delete -> delete_<model>

    Attributes:
        require_model_permissions: If True, enforce Django permissions
    """

    order = 20
    name = "model_permission"

    # Map mutation operations to Django permission codenames
    PERMISSION_MAP = {
        "create": "add",
        "update": "change",
        "delete": "delete",
    }

    def __init__(self, require_model_permissions: bool = True):
        """
        Initialize permission step.

        Args:
            require_model_permissions: If True, enforce Django model permissions
        """
        self.require_model_permissions = require_model_permissions

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Check user has required model permission.

        Args:
            ctx: Mutation context

        Returns:
            Context with potential permission error
        """
        if not self.require_model_permissions:
            return ctx

        user = ctx.user
        if user is None:
            ctx.add_error("Permission check requires authenticated user")
            return ctx

        codename = self.PERMISSION_MAP.get(ctx.operation)
        if not codename:
            return ctx

        permission = ctx.get_permission_codename()

        if not user.has_perm(permission):
            ctx.add_error(f"Permission required: {permission}")

        return ctx


class OperationGuardStep(MutationStep):
    """
    Check GraphQLMeta operation guards.

    This step invokes the model's GraphQLMeta.ensure_operation_access method
    to check any custom guards defined for the operation.

    The guard can check:
    - Operation-level guards (for all operations of a type)
    - Instance-level guards (for update/delete with existing instance)
    """

    order = 25
    name = "operation_guard"

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Check GraphQLMeta operation guards.

        Args:
            ctx: Mutation context

        Returns:
            Context with potential guard error
        """
        if ctx.graphql_meta is None:
            return ctx

        try:
            ctx.graphql_meta.ensure_operation_access(
                ctx.operation,
                info=ctx.info,
                instance=ctx.instance,
            )
        except Exception as e:
            ctx.add_error(str(e))

        return ctx


class ABACPermissionStep(MutationStep):
    """
    Hybrid RBAC+ABAC permission check in the mutation pipeline.

    This step is a no-op when ABAC is disabled in security settings.
    """

    order = 27
    name = "abac_permission"

    def execute(self, ctx: MutationContext) -> MutationContext:
        from rail_django.config_proxy import get_setting

        if not bool(get_setting("security_settings.enable_abac", False)):
            return ctx

        user = ctx.user
        if user is None:
            return ctx

        try:
            from rail_django.security.hybrid import hybrid_engine
            from rail_django.security.rbac import PermissionContext
        except Exception:
            return ctx

        permission = ctx.get_permission_codename()
        perm_context = PermissionContext(
            user=user,
            object_instance=ctx.instance,
            model_class=ctx.model,
            operation=ctx.operation,
            additional_context={"request": ctx.request},
        )

        decision = hybrid_engine.has_permission(
            user,
            permission,
            context=perm_context,
            instance=ctx.instance,
            request=ctx.request,
            info=ctx.info,
        )
        if not decision.allowed:
            ctx.add_error(
                f"Access denied by hybrid RBAC+ABAC policy: {decision.reason}",
                code="PERMISSION_DENIED",
            )

        return ctx
