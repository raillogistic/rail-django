"""
Tenant handling pipeline steps.

Injects tenant fields and applies tenant scoping for multi-tenant applications.
"""

from typing import Any, Optional

from ..base import MutationStep, OperationFilteredStep
from ..context import MutationContext


class TenantInjectionStep(MutationStep):
    """
    Inject tenant fields into input data.

    For multi-tenant applications, this step automatically adds
    tenant-related fields to the input data based on the current
    request context.
    """

    order = 50
    name = "tenant_injection"

    def __init__(self, tenant_applicator: Optional[Any] = None):
        """
        Initialize tenant injection step.

        Args:
            tenant_applicator: Object with apply_tenant_input method
        """
        self.tenant_applicator = tenant_applicator

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Inject tenant fields into input data.

        Args:
            ctx: Mutation context

        Returns:
            Context with tenant fields injected
        """
        if self.tenant_applicator is None:
            return ctx

        ctx.input_data = self.tenant_applicator.apply_tenant_input(
            ctx.input_data,
            ctx.info,
            ctx.model,
            operation=ctx.operation,
        )
        return ctx


class TenantScopeStep(OperationFilteredStep):
    """
    Apply tenant scoping to queryset.

    For update/delete operations in multi-tenant applications,
    this step applies tenant scoping to the queryset used for
    instance lookup.

    Note: The actual scoping is applied in InstanceLookupStep.
    This step stores the tenant applicator in context for use there.
    """

    order = 55
    name = "tenant_scope"
    allowed_operations = ("update", "delete")

    def __init__(self, tenant_applicator: Optional[Any] = None):
        """
        Initialize tenant scope step.

        Args:
            tenant_applicator: Object with apply_tenant_scope method
        """
        self.tenant_applicator = tenant_applicator

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Store tenant applicator for instance lookup.

        Args:
            ctx: Mutation context

        Returns:
            Context with tenant_applicator stored in extra
        """
        if self.tenant_applicator:
            ctx.extra["tenant_applicator"] = self.tenant_applicator
        return ctx
