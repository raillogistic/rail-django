"""
Execution pipeline steps.

Handles the actual create, update, and delete operations.
"""

from typing import Any, Optional

from ..base import OperationFilteredStep
from ..context import MutationContext


class CreateExecutionStep(OperationFilteredStep):
    """
    Execute the create operation.

    Creates a new model instance using either the nested operation
    handler (for complex nested creates) or direct model creation.
    """

    order = 80
    name = "create_execution"
    allowed_operations = ("create",)

    def __init__(self, nested_handler: Optional[Any] = None):
        """
        Initialize create execution step.

        Args:
            nested_handler: Optional NestedOperationHandler for nested creates
        """
        self.nested_handler = nested_handler

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Create a new model instance.

        Args:
            ctx: Mutation context

        Returns:
            Context with result populated
        """
        from ...mutations.methods import _wrap_with_audit

        def _perform_create(info, payload):
            if self.nested_handler:
                return self.nested_handler.handle_nested_create(
                    ctx.model,
                    payload,
                    info=info,
                )
            else:
                return ctx.model.objects.create(**payload)

        audited_create = _wrap_with_audit(ctx.model, "create", _perform_create)
        ctx.result = audited_create(ctx.info, ctx.input_data)

        return ctx


class UpdateExecutionStep(OperationFilteredStep):
    """
    Execute the update operation.

    Updates an existing model instance using either the nested operation
    handler (for complex nested updates) or direct field updates.
    """

    order = 80
    name = "update_execution"
    allowed_operations = ("update",)

    def __init__(self, nested_handler: Optional[Any] = None):
        """
        Initialize update execution step.

        Args:
            nested_handler: Optional NestedOperationHandler for nested updates
        """
        self.nested_handler = nested_handler

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Update an existing model instance.

        Args:
            ctx: Mutation context

        Returns:
            Context with result populated
        """
        if ctx.instance is None:
            ctx.add_error("Instance not found for update")
            return ctx

        from ...mutations.methods import _wrap_with_audit

        def _perform_update(info, target, payload):
            if self.nested_handler:
                return self.nested_handler.handle_nested_update(
                    ctx.model,
                    payload,
                    target,
                    info=info,
                )
            else:
                for key, value in payload.items():
                    setattr(target, key, value)
                target.save()
                return target

        audited_update = _wrap_with_audit(ctx.model, "update", _perform_update)
        ctx.result = audited_update(ctx.info, ctx.instance, ctx.input_data)

        return ctx


class DeleteExecutionStep(OperationFilteredStep):
    """
    Execute the delete operation.

    Deletes an existing model instance and preserves the PK
    for return value.
    """

    order = 80
    name = "delete_execution"
    allowed_operations = ("delete",)

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Delete an existing model instance.

        Args:
            ctx: Mutation context

        Returns:
            Context with result (deleted instance with preserved PK)
        """
        if ctx.instance is None:
            ctx.add_error("Instance not found for delete")
            return ctx

        from ...mutations.methods import _wrap_with_audit

        def _perform_delete(info, target):
            target_pk = target.pk
            target.delete()
            # Preserve PK for return value
            try:
                target.pk = target_pk
            except Exception:
                pass
            return target

        audited_delete = _wrap_with_audit(ctx.model, "delete", _perform_delete)
        ctx.result = audited_delete(ctx.info, ctx.instance)

        return ctx
