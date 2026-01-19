"""
Instance lookup pipeline step.

Looks up existing instances for update/delete operations.
"""

from typing import Any, Optional

from ..base import OperationFilteredStep
from ..context import MutationContext
from ..utils import decode_global_id


class InstanceLookupStep(OperationFilteredStep):
    """
    Look up existing instance for update/delete operations.

    This step retrieves the existing database instance based on the
    provided ID. It handles:
    - Direct database IDs
    - GraphQL global IDs (base64 encoded)
    - Tenant scoping if a tenant applicator is configured
    """

    order = 35  # After auth, before input processing
    name = "instance_lookup"
    allowed_operations = ("update", "delete")

    def __init__(self, tenant_applicator: Optional[Any] = None):
        """
        Initialize instance lookup step.

        Args:
            tenant_applicator: Optional object with apply_tenant_scope method
        """
        self.tenant_applicator = tenant_applicator

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Look up the instance by ID.

        Args:
            ctx: Mutation context

        Returns:
            Context with instance populated or error
        """
        if not ctx.instance_id:
            ctx.add_error("ID is required", field_name="id")
            return ctx

        queryset = ctx.model.objects.all()

        # Apply tenant scoping if available
        tenant_applicator = self.tenant_applicator or ctx.extra.get(
            "tenant_applicator"
        )
        if tenant_applicator:
            queryset = tenant_applicator.apply_tenant_scope(
                queryset,
                ctx.info,
                ctx.model,
                operation=ctx.operation,
            )

        # Try to get instance by primary key
        try:
            ctx.instance = queryset.get(pk=ctx.instance_id)
            return ctx
        except (ValueError, ctx.model.DoesNotExist):
            pass

        # Try decoding as GraphQL global ID
        _, decoded_id = decode_global_id(ctx.instance_id)
        if decoded_id != ctx.instance_id:
            try:
                ctx.instance = queryset.get(pk=decoded_id)
                return ctx
            except (ValueError, ctx.model.DoesNotExist):
                pass

        # Instance not found
        ctx.add_error(f"{ctx.model_name} with id {ctx.instance_id} does not exist")
        return ctx
