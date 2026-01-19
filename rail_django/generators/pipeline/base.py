"""
Base classes for the mutation pipeline.

Provides MutationStep abstract base class and MutationPipeline orchestrator.
"""

from abc import ABC, abstractmethod
from typing import Callable, List

from .context import MutationContext


class MutationStep(ABC):
    """
    Base class for mutation pipeline steps.

    Each step performs a specific task in the mutation process such as
    authentication, validation, permission checking, or execution.

    Attributes:
        order: Integer determining step execution order (lower = earlier)
        name: String identifier for debugging and logging

    Example:
        class MyCustomStep(MutationStep):
            order = 55
            name = "my_custom_step"

            def execute(self, ctx: MutationContext) -> MutationContext:
                # Do something with ctx
                return ctx
    """

    # Step ordering (lower = earlier in pipeline)
    order: int = 100

    # Step identifier for debugging/logging
    name: str = "base"

    @abstractmethod
    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Execute this step.

        Args:
            ctx: Current mutation context

        Returns:
            Modified context (can be same instance)
        """
        pass

    def should_run(self, ctx: MutationContext) -> bool:
        """
        Check if this step should run.

        Override to conditionally skip steps.
        Default: skip if context has abort flag set.

        Args:
            ctx: Current mutation context

        Returns:
            True if step should execute, False to skip
        """
        return not ctx.should_abort

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} order={self.order} name={self.name}>"


class MutationPipeline:
    """
    Executes an ordered sequence of mutation steps.

    The pipeline sorts steps by their order attribute and executes them
    sequentially. If any step sets should_abort=True on the context,
    subsequent steps will be skipped (unless they override should_run).

    Example:
        pipeline = MutationPipeline([
            AuthenticationStep(),
            PermissionStep(),
            ValidationStep(),
            ExecutionStep(),
        ])
        result_ctx = pipeline.execute(initial_ctx)
    """

    def __init__(self, steps: List[MutationStep]):
        """
        Initialize pipeline with steps.

        Args:
            steps: List of MutationStep instances (will be sorted by order)
        """
        # Sort steps by order
        self.steps = sorted(steps, key=lambda s: s.order)

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Execute all steps in order.

        Stops early if any step sets should_abort=True on the context.

        Args:
            ctx: Initial mutation context

        Returns:
            Final mutation context after all steps
        """
        for step in self.steps:
            if step.should_run(ctx):
                ctx = step.execute(ctx)
        return ctx

    def get_step_names(self) -> List[str]:
        """
        Get ordered list of step names.

        Returns:
            List of step name strings
        """
        return [s.name for s in self.steps]

    def __repr__(self) -> str:
        step_names = self.get_step_names()
        return f"<MutationPipeline steps={step_names}>"


class ConditionalStep(MutationStep):
    """
    Wraps a step with a custom condition function.

    Useful for conditionally including steps without subclassing.

    Example:
        step = ConditionalStep(
            AuditStep(),
            condition=lambda ctx: ctx.graphql_meta.audit_enabled
        )
    """

    def __init__(
        self,
        step: MutationStep,
        condition: Callable[[MutationContext], bool],
    ):
        """
        Initialize conditional wrapper.

        Args:
            step: The step to wrap
            condition: Function that returns True if step should run
        """
        self._step = step
        self._condition = condition
        self.order = step.order
        self.name = f"conditional:{step.name}"

    def should_run(self, ctx: MutationContext) -> bool:
        """Check both base condition and custom condition."""
        return super().should_run(ctx) and self._condition(ctx)

    def execute(self, ctx: MutationContext) -> MutationContext:
        """Delegate execution to wrapped step."""
        return self._step.execute(ctx)


class OperationFilteredStep(MutationStep):
    """
    A step that only runs for specific operations.

    Base class for steps that should only run during create, update, or delete.

    Example:
        class CreateOnlyStep(OperationFilteredStep):
            allowed_operations = ("create",)
            name = "create_only"

            def execute(self, ctx):
                # Only runs during create
                return ctx
    """

    # Override in subclass to filter operations
    allowed_operations: tuple = ("create", "update", "delete")

    def should_run(self, ctx: MutationContext) -> bool:
        """Check operation is in allowed list."""
        return super().should_run(ctx) and ctx.operation in self.allowed_operations
