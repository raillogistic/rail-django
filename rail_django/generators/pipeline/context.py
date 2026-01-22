"""
MutationContext - Carries state through the mutation pipeline.

The context is created at the start of a mutation and passed through each pipeline step.
Each step can read from and modify the context as needed.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import graphene
    from django.db import models
    from ..mutations.errors import MutationError


@dataclass
class MutationContext:
    """
    Carries state through the mutation pipeline.

    This context object is created at the start of a mutation and passed
    through each pipeline step. Steps can read from and modify the context
    as needed.

    Attributes:
        info: GraphQL resolve info containing request context
        model: The Django model class being mutated
        operation: The operation type ("create", "update", "delete")
        raw_input: Original input data (immutable reference)
        input_data: Transformed input data (mutable)
        instance: Existing instance for update/delete operations
        instance_id: ID of instance to look up for update/delete
        result: The resulting model instance after mutation
        errors: List of mutation errors
        should_abort: Flag indicating pipeline should stop
        graphql_meta: GraphQLMeta configuration for the model
        settings: Mutation generator settings
        extra: Dictionary for storing additional step-specific data
    """

    # Request context
    info: "graphene.ResolveInfo"

    # Model context
    model: type["models.Model"]
    operation: str  # "create", "update", "delete"

    # Data flow
    raw_input: dict[str, Any]  # Original input (immutable reference)
    input_data: dict[str, Any]  # Transformed input (mutable)

    # Instance (for update/delete)
    instance: Optional["models.Model"] = None
    instance_id: Optional[str] = None

    # Result
    result: Optional["models.Model"] = None

    # Error handling
    errors: list["MutationError"] = field(default_factory=list)
    should_abort: bool = False

    # Metadata
    graphql_meta: Any = None
    settings: Any = None

    # Extra storage for step-specific data
    extra: dict[str, Any] = field(default_factory=dict)

    def add_error(self, message: str, field_name: Optional[str] = None) -> None:
        """
        Add an error and set abort flag.

        Args:
            message: Error message
            field_name: Optional field name the error relates to
        """
        from ..mutations.errors import MutationError

        self.errors.append(MutationError(field=field_name, message=message))
        self.should_abort = True

    def add_errors(self, errors: list["MutationError"]) -> None:
        """
        Add multiple errors and set abort flag if any errors added.

        Args:
            errors: List of MutationError objects
        """
        self.errors.extend(errors)
        if errors:
            self.should_abort = True

    def add_warning(self, message: str, field_name: Optional[str] = None) -> None:
        """
        Add a warning (non-fatal error that doesn't abort).

        Args:
            message: Warning message
            field_name: Optional field name the warning relates to
        """
        from ..mutations.errors import MutationError

        self.errors.append(MutationError(field=field_name, message=message))
        # Note: Does NOT set should_abort

    @property
    def user(self) -> Any:
        """Convenience accessor for request user."""
        return getattr(self.info.context, "user", None)

    @property
    def request(self) -> Any:
        """Convenience accessor for the request object."""
        return getattr(self.info.context, "request", self.info.context)

    @property
    def model_name(self) -> str:
        """Return the model class name."""
        return self.model.__name__

    @property
    def app_label(self) -> str:
        """Return the model's app label."""
        return self.model._meta.app_label

    @property
    def model_name_lower(self) -> str:
        """Return the lowercase model name."""
        return self.model._meta.model_name

    def get_permission_codename(self) -> str:
        """
        Get the permission codename for the current operation.

        Returns:
            Permission string like 'app_label.add_modelname'
        """
        permission_map = {
            "create": "add",
            "update": "change",
            "delete": "delete",
        }
        codename = permission_map.get(self.operation, self.operation)
        return f"{self.app_label}.{codename}_{self.model_name_lower}"

    def copy_with(self, **overrides) -> "MutationContext":
        """
        Create a copy of this context with specified overrides.

        Args:
            **overrides: Fields to override in the copy

        Returns:
            New MutationContext with overridden values
        """
        from dataclasses import asdict

        data = asdict(self)
        data.update(overrides)
        return MutationContext(**data)
