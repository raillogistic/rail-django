# Mutation Generation Refactoring Plan

## Overview

Replace the current closure-based mutation generation with a **Pipeline-Based Architecture** that provides composable, testable, and extensible mutation handling while maintaining full backward compatibility with existing auto-generation from Django models.

---

## Current Problems

| Problem | Impact |
|---------|--------|
| **Closure-based class generation** | Hard to debug, can't subclass, implicit dependencies |
| **Code duplication** | `_sanitize_input_data`, `_normalize_enum_inputs`, `_process_dual_fields`, `_get_nested_handler` duplicated across Create/Update |
| **Monolithic mutate()** | 7+ transformation steps in one method, hard to follow |
| **Hardcoded logic** | `_get_mandatory_fields` has hardcoded model names |
| **Mixed responsibilities** | Validation, transformation, permission, nested ops, audit all in one place |
| **Non-composable** | Can't customize one step without overriding everything |

---

## New Architecture

### Core Concepts

```
┌─────────────────────────────────────────────────────────────────┐
│                      MutationContext                            │
│  Carries state through pipeline: info, model, input, errors     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MutationPipeline                           │
│  Executes ordered list of MutationStep instances                │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ AuthStep      │   │ ValidateStep  │   │ ExecuteStep   │
│               │──▶│               │──▶│               │
└───────────────┘   └───────────────┘   └───────────────┘
```

### Key Components

1. **MutationContext** - Immutable-ish dataclass carrying state through pipeline
2. **MutationStep** - Abstract base for each pipeline step
3. **MutationPipeline** - Orchestrates step execution
4. **MutationStepRegistry** - Collects and orders steps
5. **BaseMutation** - Clean base class for generated mutations
6. **MutationFactory** - Generates mutation classes using pipeline

---

## File Structure

```
rail_django/generators/
├── mutations.py                    # Main MutationGenerator (update to use new system)
├── mutations_crud.py               # REMOVE after migration
├── mutations_bulk.py               # Update to use pipeline
├── mutations_methods.py            # Keep (method mutations)
├── mutations_errors.py             # Keep (error types)
├── mutations_limits.py             # Keep (limit validation)
│
├── pipeline/                       # NEW: Pipeline module
│   ├── __init__.py
│   ├── context.py                  # MutationContext dataclass
│   ├── base.py                     # MutationStep ABC, MutationPipeline
│   ├── registry.py                 # Step registry and ordering
│   │
│   ├── steps/                      # Individual pipeline steps
│   │   ├── __init__.py
│   │   ├── authentication.py       # AuthenticationStep
│   │   ├── permissions.py          # PermissionStep, ModelPermissionStep
│   │   ├── sanitization.py         # InputSanitizationStep
│   │   ├── normalization.py        # EnumNormalizationStep, DualFieldStep
│   │   ├── validation.py           # ValidationStep, NestedLimitStep
│   │   ├── tenant.py               # TenantInjectionStep, TenantScopeStep
│   │   ├── lookup.py               # InstanceLookupStep (for update/delete)
│   │   ├── execution.py            # CreateStep, UpdateStep, DeleteStep
│   │   └── audit.py                # AuditStep
│   │
│   └── factories/                  # Mutation class factories
│       ├── __init__.py
│       ├── base.py                 # BaseMutation class
│       ├── create.py               # CreateMutationFactory
│       ├── update.py               # UpdateMutationFactory
│       └── delete.py               # DeleteMutationFactory
```

---

## Implementation Plan

### Phase 1: Foundation (No Breaking Changes)

#### Step 1.1: Create MutationContext

**File:** `rail_django/generators/pipeline/context.py`

```python
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING
import graphene
from django.db import models

if TYPE_CHECKING:
    from ..mutations_errors import MutationError

@dataclass
class MutationContext:
    """Carries state through the mutation pipeline."""

    # Request context
    info: graphene.ResolveInfo

    # Model context
    model: type[models.Model]
    operation: str  # "create", "update", "delete"

    # Data flow
    raw_input: dict[str, Any]  # Original input (immutable reference)
    input_data: dict[str, Any]  # Transformed input (mutable)

    # Instance (for update/delete)
    instance: Optional[models.Model] = None
    instance_id: Optional[str] = None

    # Result
    result: Optional[models.Model] = None

    # Error handling
    errors: list["MutationError"] = field(default_factory=list)
    should_abort: bool = False

    # Metadata
    graphql_meta: Any = None
    settings: Any = None

    def add_error(self, message: str, field: Optional[str] = None) -> None:
        """Add an error and set abort flag."""
        from ..mutations_errors import MutationError
        self.errors.append(MutationError(field=field, message=message))
        self.should_abort = True

    def add_errors(self, errors: list["MutationError"]) -> None:
        """Add multiple errors and set abort flag."""
        self.errors.extend(errors)
        if errors:
            self.should_abort = True

    @property
    def user(self):
        """Convenience accessor for request user."""
        return getattr(self.info.context, "user", None)

    @property
    def model_name(self) -> str:
        return self.model.__name__
```

#### Step 1.2: Create MutationStep Base and Pipeline

**File:** `rail_django/generators/pipeline/base.py`

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Callable
from .context import MutationContext


class MutationStep(ABC):
    """Base class for mutation pipeline steps."""

    # Step ordering (lower = earlier)
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
        Default: skip if context has abort flag.
        """
        return not ctx.should_abort

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} order={self.order}>"


class MutationPipeline:
    """Executes an ordered sequence of mutation steps."""

    def __init__(self, steps: List[MutationStep]):
        # Sort steps by order
        self.steps = sorted(steps, key=lambda s: s.order)

    def execute(self, ctx: MutationContext) -> MutationContext:
        """
        Execute all steps in order.

        Stops early if any step sets should_abort=True.
        """
        for step in self.steps:
            if step.should_run(ctx):
                ctx = step.execute(ctx)
        return ctx

    def __repr__(self) -> str:
        step_names = [s.name for s in self.steps]
        return f"<MutationPipeline steps={step_names}>"


class ConditionalStep(MutationStep):
    """Wraps a step with a custom condition."""

    def __init__(self, step: MutationStep, condition: Callable[[MutationContext], bool]):
        self._step = step
        self._condition = condition
        self.order = step.order
        self.name = f"conditional:{step.name}"

    def should_run(self, ctx: MutationContext) -> bool:
        return super().should_run(ctx) and self._condition(ctx)

    def execute(self, ctx: MutationContext) -> MutationContext:
        return self._step.execute(ctx)
```

#### Step 1.3: Extract Shared Utilities

**File:** `rail_django/generators/pipeline/utils.py`

Extract duplicated methods from `mutations_crud.py` into standalone functions:

```python
from typing import Any
from django.db import models


def sanitize_input_data(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize input data to handle special characters.

    - Converts ID to string if present
    - Handles double quote escaping
    - Recursively processes nested structures
    """
    result = input_data.copy()

    if "id" in result and not isinstance(result["id"], str):
        result["id"] = str(result["id"])

    def sanitize_value(value):
        if isinstance(value, str):
            return value.replace('""', '"')
        if isinstance(value, dict):
            return {k: sanitize_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [sanitize_value(item) for item in value]
        return value

    return {k: sanitize_value(v) for k, v in result.items()}


def normalize_enum_inputs(input_data: dict[str, Any], model: type[models.Model]) -> dict[str, Any]:
    """
    Normalize GraphQL Enum inputs to their underlying Django field values.
    """
    normalized = input_data.copy()

    choice_fields = {
        f.name: f
        for f in model._meta.get_fields()
        if hasattr(f, "choices") and getattr(f, "choices", None)
    }

    def normalize_value(value: Any) -> Any:
        if hasattr(value, "value") and not isinstance(value, (str, bytes)):
            try:
                return getattr(value, "value")
            except Exception:
                return value
        if isinstance(value, list):
            return [normalize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: normalize_value(v) for k, v in value.items()}
        return value

    for field_name in choice_fields:
        if field_name in normalized:
            normalized[field_name] = normalize_value(normalized[field_name])

    return normalized


def process_dual_fields(
    input_data: dict[str, Any],
    model: type[models.Model],
    introspector=None,
) -> dict[str, Any]:
    """
    Process dual fields (nested_X vs X) with validation.

    Raises:
        ValidationError: If both nested and direct field provided
    """
    from django.core.exceptions import ValidationError
    from .introspector import ModelIntrospector

    if introspector is None:
        introspector = ModelIntrospector.for_model(model)

    processed = input_data.copy()
    relationships = introspector.get_model_relationships()

    for field_name, rel_info in relationships.items():
        nested_field_name = f"nested_{field_name}"

        if rel_info.relationship_type in ["ForeignKey", "OneToOneField"]:
            has_direct = field_name in processed and processed[field_name] is not None
            has_nested = nested_field_name in processed and processed[nested_field_name] is not None

            if has_direct and has_nested:
                raise ValidationError({
                    field_name: f"Cannot provide both '{field_name}' and '{nested_field_name}'."
                })

            if has_nested:
                processed[field_name] = processed.pop(nested_field_name)

        elif rel_info.relationship_type == "ManyToManyField":
            if nested_field_name in processed:
                processed[field_name] = processed.pop(nested_field_name)

    # Handle reverse relationships
    for field_name, _ in introspector.get_reverse_relations().items():
        nested_field_name = f"nested_{field_name}"
        if nested_field_name in processed:
            processed[field_name] = processed.pop(nested_field_name)

    return processed


def get_mandatory_fields(model: type[models.Model], graphql_meta=None) -> list[str]:
    """
    Get mandatory fields from model's GraphQLMeta configuration.

    Replaces hardcoded model name checks.
    """
    if graphql_meta is None:
        from ..core.meta import get_model_graphql_meta
        graphql_meta = get_model_graphql_meta(model)

    # Read from GraphQLMeta configuration
    field_config = getattr(graphql_meta, "field_config", None)
    if field_config:
        mandatory = getattr(field_config, "mandatory", None)
        if mandatory:
            return list(mandatory)

    # Fallback: derive from model field definitions
    mandatory = []
    for field in model._meta.get_fields():
        if hasattr(field, "null") and hasattr(field, "blank"):
            if not field.null and not field.blank and not getattr(field, "has_default", lambda: False)():
                if hasattr(field, "remote_field") and field.remote_field:
                    mandatory.append(field.name)

    return mandatory
```

### Phase 2: Implement Pipeline Steps

#### Step 2.1: Authentication & Permission Steps

**File:** `rail_django/generators/pipeline/steps/authentication.py`

```python
from ..base import MutationStep
from ..context import MutationContext


class AuthenticationStep(MutationStep):
    """Verify user is authenticated."""

    order = 10
    name = "authentication"

    def __init__(self, require_authentication: bool = True):
        self.require_authentication = require_authentication

    def execute(self, ctx: MutationContext) -> MutationContext:
        if not self.require_authentication:
            return ctx

        user = ctx.user
        if user is None or not getattr(user, "is_authenticated", False):
            ctx.add_error("Authentication required")

        return ctx
```

**File:** `rail_django/generators/pipeline/steps/permissions.py`

```python
from ..base import MutationStep
from ..context import MutationContext


class ModelPermissionStep(MutationStep):
    """Check Django model permissions (add, change, delete)."""

    order = 20
    name = "model_permission"

    PERMISSION_MAP = {
        "create": "add",
        "update": "change",
        "delete": "delete",
    }

    def __init__(self, require_model_permissions: bool = True):
        self.require_model_permissions = require_model_permissions

    def execute(self, ctx: MutationContext) -> MutationContext:
        if not self.require_model_permissions:
            return ctx

        user = ctx.user
        if user is None:
            ctx.add_error("Permission check requires authenticated user")
            return ctx

        codename = self.PERMISSION_MAP.get(ctx.operation)
        if not codename:
            return ctx

        app_label = ctx.model._meta.app_label
        model_name = ctx.model._meta.model_name
        permission = f"{app_label}.{codename}_{model_name}"

        if not user.has_perm(permission):
            ctx.add_error(f"Permission required: {permission}")

        return ctx


class OperationGuardStep(MutationStep):
    """Check GraphQLMeta operation guards."""

    order = 25
    name = "operation_guard"

    def execute(self, ctx: MutationContext) -> MutationContext:
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
```

#### Step 2.2: Input Processing Steps

**File:** `rail_django/generators/pipeline/steps/sanitization.py`

```python
from ..base import MutationStep
from ..context import MutationContext
from ..utils import sanitize_input_data


class InputSanitizationStep(MutationStep):
    """Sanitize input data (escape quotes, convert IDs)."""

    order = 30
    name = "sanitization"

    def execute(self, ctx: MutationContext) -> MutationContext:
        ctx.input_data = sanitize_input_data(ctx.input_data)
        return ctx
```

**File:** `rail_django/generators/pipeline/steps/normalization.py`

```python
from ..base import MutationStep
from ..context import MutationContext
from ..utils import normalize_enum_inputs, process_dual_fields


class EnumNormalizationStep(MutationStep):
    """Convert GraphQL enums to Django field values."""

    order = 40
    name = "enum_normalization"

    def execute(self, ctx: MutationContext) -> MutationContext:
        ctx.input_data = normalize_enum_inputs(ctx.input_data, ctx.model)
        return ctx


class DualFieldProcessingStep(MutationStep):
    """Process nested_X vs X field priority."""

    order = 45
    name = "dual_field_processing"

    def execute(self, ctx: MutationContext) -> MutationContext:
        from django.core.exceptions import ValidationError
        from ...mutations_errors import build_validation_errors

        try:
            ctx.input_data = process_dual_fields(ctx.input_data, ctx.model)
        except ValidationError as e:
            ctx.add_errors(build_validation_errors(e))

        return ctx


class ReadOnlyFieldFilterStep(MutationStep):
    """Remove read-only fields from input."""

    order = 48
    name = "read_only_filter"

    def execute(self, ctx: MutationContext) -> MutationContext:
        if ctx.graphql_meta is None:
            return ctx

        field_config = getattr(ctx.graphql_meta, "field_config", None)
        if not field_config:
            return ctx

        read_only = set(getattr(field_config, "read_only", []) or [])
        if read_only:
            ctx.input_data = {
                k: v for k, v in ctx.input_data.items()
                if k not in read_only
            }

        return ctx
```

#### Step 2.3: Tenant & Validation Steps

**File:** `rail_django/generators/pipeline/steps/tenant.py`

```python
from ..base import MutationStep
from ..context import MutationContext


class TenantInjectionStep(MutationStep):
    """Inject tenant fields into input data."""

    order = 50
    name = "tenant_injection"

    def __init__(self, tenant_applicator=None):
        self.tenant_applicator = tenant_applicator

    def execute(self, ctx: MutationContext) -> MutationContext:
        if self.tenant_applicator is None:
            return ctx

        ctx.input_data = self.tenant_applicator.apply_tenant_input(
            ctx.input_data,
            ctx.info,
            ctx.model,
            operation=ctx.operation,
        )
        return ctx


class TenantScopeStep(MutationStep):
    """Apply tenant scoping to queryset (for update/delete lookup)."""

    order = 55
    name = "tenant_scope"

    def __init__(self, tenant_applicator=None):
        self.tenant_applicator = tenant_applicator

    def should_run(self, ctx: MutationContext) -> bool:
        # Only for update/delete which need instance lookup
        return super().should_run(ctx) and ctx.operation in ("update", "delete")

    def execute(self, ctx: MutationContext) -> MutationContext:
        # Tenant scoping is applied in InstanceLookupStep
        return ctx
```

**File:** `rail_django/generators/pipeline/steps/validation.py`

```python
from ..base import MutationStep
from ..context import MutationContext


class InputValidationStep(MutationStep):
    """Run input validator on mutation data."""

    order = 60
    name = "input_validation"

    def __init__(self, input_validator=None):
        self.input_validator = input_validator

    def execute(self, ctx: MutationContext) -> MutationContext:
        if self.input_validator is None:
            return ctx

        ctx.input_data = self.input_validator.validate_and_sanitize(
            ctx.model.__name__,
            ctx.input_data,
        )
        return ctx


class NestedLimitValidationStep(MutationStep):
    """Validate nested operation limits."""

    order = 65
    name = "nested_limit_validation"

    def __init__(self, nested_handler=None):
        self.nested_handler = nested_handler

    def execute(self, ctx: MutationContext) -> MutationContext:
        if self.nested_handler is None:
            return ctx

        from ...mutations_limits import _get_nested_validation_limits, _validate_nested_limits

        limits = _get_nested_validation_limits(ctx.info, self.nested_handler)
        errors = _validate_nested_limits(ctx.input_data, limits)

        if errors:
            ctx.add_errors(errors)

        return ctx


class NestedDataValidationStep(MutationStep):
    """Validate nested data structure before processing."""

    order = 70
    name = "nested_data_validation"

    def __init__(self, nested_handler=None):
        self.nested_handler = nested_handler

    def execute(self, ctx: MutationContext) -> MutationContext:
        if self.nested_handler is None:
            return ctx

        from ...mutations_errors import build_error_list

        validation_errors = self.nested_handler.validate_nested_data(
            ctx.model,
            ctx.input_data,
            ctx.operation,
        )

        if validation_errors:
            ctx.add_errors(build_error_list(validation_errors))

        return ctx
```

#### Step 2.4: Instance Lookup Step (Update/Delete)

**File:** `rail_django/generators/pipeline/steps/lookup.py`

```python
from ..base import MutationStep
from ..context import MutationContext


class InstanceLookupStep(MutationStep):
    """Look up existing instance for update/delete operations."""

    order = 35  # After auth, before input processing
    name = "instance_lookup"

    def __init__(self, tenant_applicator=None):
        self.tenant_applicator = tenant_applicator

    def should_run(self, ctx: MutationContext) -> bool:
        return super().should_run(ctx) and ctx.operation in ("update", "delete")

    def execute(self, ctx: MutationContext) -> MutationContext:
        if not ctx.instance_id:
            ctx.add_error("ID is required", field="id")
            return ctx

        queryset = ctx.model.objects.all()

        # Apply tenant scoping if available
        if self.tenant_applicator:
            queryset = self.tenant_applicator.apply_tenant_scope(
                queryset,
                ctx.info,
                ctx.model,
                operation=ctx.operation,
            )

        try:
            ctx.instance = queryset.get(pk=ctx.instance_id)
        except (ValueError, ctx.model.DoesNotExist):
            # Try decoding as GraphQL global ID
            try:
                from graphql_relay import from_global_id
                _, decoded_id = from_global_id(ctx.instance_id)
                ctx.instance = queryset.get(pk=decoded_id)
            except Exception:
                ctx.add_error(
                    f"{ctx.model_name} with id {ctx.instance_id} does not exist"
                )

        return ctx
```

#### Step 2.5: Execution Steps

**File:** `rail_django/generators/pipeline/steps/execution.py`

```python
from ..base import MutationStep
from ..context import MutationContext


class CreateExecutionStep(MutationStep):
    """Execute the create operation."""

    order = 80
    name = "create_execution"

    def __init__(self, nested_handler=None):
        self.nested_handler = nested_handler

    def should_run(self, ctx: MutationContext) -> bool:
        return super().should_run(ctx) and ctx.operation == "create"

    def execute(self, ctx: MutationContext) -> MutationContext:
        if self.nested_handler:
            ctx.result = self.nested_handler.handle_nested_create(
                ctx.model,
                ctx.input_data,
                info=ctx.info,
            )
        else:
            ctx.result = ctx.model.objects.create(**ctx.input_data)

        return ctx


class UpdateExecutionStep(MutationStep):
    """Execute the update operation."""

    order = 80
    name = "update_execution"

    def __init__(self, nested_handler=None):
        self.nested_handler = nested_handler

    def should_run(self, ctx: MutationContext) -> bool:
        return super().should_run(ctx) and ctx.operation == "update"

    def execute(self, ctx: MutationContext) -> MutationContext:
        if ctx.instance is None:
            ctx.add_error("Instance not found for update")
            return ctx

        if self.nested_handler:
            ctx.result = self.nested_handler.handle_nested_update(
                ctx.model,
                ctx.input_data,
                ctx.instance,
                info=ctx.info,
            )
        else:
            for key, value in ctx.input_data.items():
                setattr(ctx.instance, key, value)
            ctx.instance.save()
            ctx.result = ctx.instance

        return ctx


class DeleteExecutionStep(MutationStep):
    """Execute the delete operation."""

    order = 80
    name = "delete_execution"

    def should_run(self, ctx: MutationContext) -> bool:
        return super().should_run(ctx) and ctx.operation == "delete"

    def execute(self, ctx: MutationContext) -> MutationContext:
        if ctx.instance is None:
            ctx.add_error("Instance not found for delete")
            return ctx

        instance_pk = ctx.instance.pk
        ctx.instance.delete()

        # Preserve PK for return value
        try:
            ctx.instance.pk = instance_pk
        except Exception:
            pass

        ctx.result = ctx.instance
        return ctx
```

#### Step 2.6: Audit Step

**File:** `rail_django/generators/pipeline/steps/audit.py`

```python
from ..base import MutationStep
from ..context import MutationContext


class AuditStep(MutationStep):
    """Log mutation to audit system."""

    order = 90  # After execution
    name = "audit"

    def should_run(self, ctx: MutationContext) -> bool:
        # Only audit successful operations
        return super().should_run(ctx) and ctx.result is not None

    def execute(self, ctx: MutationContext) -> MutationContext:
        from ...mutations_methods import _wrap_with_audit

        # Audit is already handled in execution steps via wrapper
        # This step is for additional audit logging if needed

        return ctx
```

### Phase 3: Pipeline Factory

#### Step 3.1: Create Pipeline Builder

**File:** `rail_django/generators/pipeline/builder.py`

```python
from typing import List, Optional, Type
from django.db import models

from .base import MutationStep, MutationPipeline
from .steps.authentication import AuthenticationStep
from .steps.permissions import ModelPermissionStep, OperationGuardStep
from .steps.sanitization import InputSanitizationStep
from .steps.normalization import EnumNormalizationStep, DualFieldProcessingStep, ReadOnlyFieldFilterStep
from .steps.validation import InputValidationStep, NestedLimitValidationStep, NestedDataValidationStep
from .steps.tenant import TenantInjectionStep
from .steps.lookup import InstanceLookupStep
from .steps.execution import CreateExecutionStep, UpdateExecutionStep, DeleteExecutionStep
from .steps.audit import AuditStep


class PipelineBuilder:
    """Builds mutation pipelines with configurable steps."""

    def __init__(self, settings=None):
        self.settings = settings
        self._custom_steps: List[MutationStep] = []

    def add_step(self, step: MutationStep) -> "PipelineBuilder":
        """Add a custom step to the pipeline."""
        self._custom_steps.append(step)
        return self

    def build_create_pipeline(
        self,
        model: type[models.Model],
        nested_handler=None,
        input_validator=None,
        tenant_applicator=None,
    ) -> MutationPipeline:
        """Build pipeline for create mutations."""
        steps = [
            AuthenticationStep(),
            ModelPermissionStep(),
            OperationGuardStep(),
            InputSanitizationStep(),
            EnumNormalizationStep(),
            DualFieldProcessingStep(),
            ReadOnlyFieldFilterStep(),
            TenantInjectionStep(tenant_applicator),
            InputValidationStep(input_validator),
            NestedLimitValidationStep(nested_handler),
            NestedDataValidationStep(nested_handler),
            CreateExecutionStep(nested_handler),
            AuditStep(),
            *self._custom_steps,
        ]
        return MutationPipeline(steps)

    def build_update_pipeline(
        self,
        model: type[models.Model],
        nested_handler=None,
        input_validator=None,
        tenant_applicator=None,
    ) -> MutationPipeline:
        """Build pipeline for update mutations."""
        steps = [
            AuthenticationStep(),
            ModelPermissionStep(),
            InstanceLookupStep(tenant_applicator),  # Lookup before guard
            OperationGuardStep(),  # Guard can check instance
            InputSanitizationStep(),
            EnumNormalizationStep(),
            DualFieldProcessingStep(),
            ReadOnlyFieldFilterStep(),
            TenantInjectionStep(tenant_applicator),
            InputValidationStep(input_validator),
            NestedLimitValidationStep(nested_handler),
            NestedDataValidationStep(nested_handler),
            UpdateExecutionStep(nested_handler),
            AuditStep(),
            *self._custom_steps,
        ]
        return MutationPipeline(steps)

    def build_delete_pipeline(
        self,
        model: type[models.Model],
        tenant_applicator=None,
    ) -> MutationPipeline:
        """Build pipeline for delete mutations."""
        steps = [
            AuthenticationStep(),
            ModelPermissionStep(),
            InstanceLookupStep(tenant_applicator),
            OperationGuardStep(),
            DeleteExecutionStep(),
            AuditStep(),
            *self._custom_steps,
        ]
        return MutationPipeline(steps)
```

### Phase 4: New Mutation Classes

#### Step 4.1: Base Mutation Class

**File:** `rail_django/generators/pipeline/factories/base.py`

```python
from typing import Any, Optional, Type
import graphene
from django.db import models, transaction

from ..context import MutationContext
from ..base import MutationPipeline
from ...mutations_errors import MutationError, build_validation_errors, build_integrity_errors


class BasePipelineMutation(graphene.Mutation):
    """
    Base mutation class using pipeline architecture.

    Subclasses must define:
    - model_class: The Django model
    - pipeline: The MutationPipeline to execute
    - operation: "create", "update", or "delete"
    """

    # Class attributes set by factory
    model_class: Type[models.Model] = None
    pipeline: MutationPipeline = None
    operation: str = None
    graphql_meta: Any = None

    # Standard return fields
    ok = graphene.Boolean()
    errors = graphene.List(MutationError)

    @classmethod
    def build_context(
        cls,
        info: graphene.ResolveInfo,
        input_data: dict[str, Any],
        instance_id: Optional[str] = None,
    ) -> MutationContext:
        """Build initial mutation context."""
        return MutationContext(
            info=info,
            model=cls.model_class,
            operation=cls.operation,
            raw_input=input_data.copy(),
            input_data=input_data.copy(),
            instance_id=instance_id,
            graphql_meta=cls.graphql_meta,
        )

    @classmethod
    def execute_pipeline(cls, ctx: MutationContext) -> MutationContext:
        """Execute the mutation pipeline."""
        return cls.pipeline.execute(ctx)

    @classmethod
    def build_response(cls, ctx: MutationContext):
        """Build mutation response from context."""
        raise NotImplementedError("Subclasses must implement build_response")

    @classmethod
    @transaction.atomic
    def mutate(cls, root, info, **kwargs):
        """Standard mutation entry point."""
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError

        try:
            # Build context from arguments
            input_data = kwargs.get("input", {})
            instance_id = kwargs.get("id")

            ctx = cls.build_context(info, input_data, instance_id)

            # Execute pipeline
            ctx = cls.execute_pipeline(ctx)

            # Build response
            return cls.build_response(ctx)

        except ValidationError as exc:
            return cls(ok=False, object=None, errors=build_validation_errors(exc))

        except IntegrityError as exc:
            transaction.set_rollback(True)
            return cls(ok=False, object=None, errors=build_integrity_errors(cls.model_class, exc))

        except Exception as exc:
            transaction.set_rollback(True)
            return cls(
                ok=False,
                object=None,
                errors=[MutationError(field=None, message=str(exc))],
            )
```

#### Step 4.2: Mutation Factories

**File:** `rail_django/generators/pipeline/factories/create.py`

```python
from typing import Type
import graphene
from django.db import models

from .base import BasePipelineMutation
from ..builder import PipelineBuilder
from ...mutations_errors import MutationError


def create_mutation_factory(
    model: Type[models.Model],
    model_type: Type[graphene.ObjectType],
    input_type: Type[graphene.InputObjectType],
    graphql_meta,
    pipeline_builder: PipelineBuilder,
    nested_handler=None,
    input_validator=None,
    tenant_applicator=None,
) -> Type[graphene.Mutation]:
    """
    Factory function to create a CreateMutation class for a model.

    Returns a concrete mutation class with explicit attributes (no closures).
    """
    model_name = model.__name__

    # Build the pipeline
    pipeline = pipeline_builder.build_create_pipeline(
        model,
        nested_handler=nested_handler,
        input_validator=input_validator,
        tenant_applicator=tenant_applicator,
    )

    class CreateMutation(BasePipelineMutation):
        model_class = model
        operation = "create"
        graphql_meta = graphql_meta

        class Arguments:
            input = input_type(required=True)

        object = graphene.Field(model_type)

        @classmethod
        def build_response(cls, ctx):
            if ctx.should_abort:
                return cls(ok=False, object=None, errors=ctx.errors)
            return cls(ok=True, object=ctx.result, errors=None)

    # Set pipeline after class creation (avoids closure)
    CreateMutation.pipeline = pipeline

    # Create named class
    return type(
        f"Create{model_name}",
        (CreateMutation,),
        {"__doc__": f"Create a new {model_name} instance"},
    )
```

**File:** `rail_django/generators/pipeline/factories/update.py`

```python
def update_mutation_factory(
    model: Type[models.Model],
    model_type: Type[graphene.ObjectType],
    input_type: Type[graphene.InputObjectType],
    graphql_meta,
    pipeline_builder: PipelineBuilder,
    nested_handler=None,
    input_validator=None,
    tenant_applicator=None,
) -> Type[graphene.Mutation]:
    """Factory function to create an UpdateMutation class."""
    model_name = model.__name__

    pipeline = pipeline_builder.build_update_pipeline(
        model,
        nested_handler=nested_handler,
        input_validator=input_validator,
        tenant_applicator=tenant_applicator,
    )

    class UpdateMutation(BasePipelineMutation):
        model_class = model
        operation = "update"
        graphql_meta = graphql_meta

        class Arguments:
            id = graphene.ID(required=True)
            input = input_type(required=True)

        object = graphene.Field(model_type)

        @classmethod
        def build_response(cls, ctx):
            if ctx.should_abort:
                return cls(ok=False, object=None, errors=ctx.errors)
            return cls(ok=True, object=ctx.result, errors=None)

    UpdateMutation.pipeline = pipeline

    return type(
        f"Update{model_name}",
        (UpdateMutation,),
        {"__doc__": f"Update an existing {model_name} instance"},
    )
```

**File:** `rail_django/generators/pipeline/factories/delete.py`

```python
def delete_mutation_factory(
    model: Type[models.Model],
    model_type: Type[graphene.ObjectType],
    graphql_meta,
    pipeline_builder: PipelineBuilder,
    tenant_applicator=None,
) -> Type[graphene.Mutation]:
    """Factory function to create a DeleteMutation class."""
    model_name = model.__name__

    pipeline = pipeline_builder.build_delete_pipeline(
        model,
        tenant_applicator=tenant_applicator,
    )

    class DeleteMutation(BasePipelineMutation):
        model_class = model
        operation = "delete"
        graphql_meta = graphql_meta

        class Arguments:
            id = graphene.ID(required=True)

        object = graphene.Field(model_type)

        @classmethod
        def build_response(cls, ctx):
            if ctx.should_abort:
                return cls(ok=False, object=None, errors=ctx.errors)
            return cls(ok=True, object=ctx.result, errors=None)

    DeleteMutation.pipeline = pipeline

    return type(
        f"Delete{model_name}",
        (DeleteMutation,),
        {"__doc__": f"Delete a {model_name} instance"},
    )
```

### Phase 5: Update MutationGenerator

#### Step 5.1: Refactor MutationGenerator to Use Pipeline

**File:** `rail_django/generators/mutations.py` (updated)

```python
from .pipeline.builder import PipelineBuilder
from .pipeline.factories.create import create_mutation_factory
from .pipeline.factories.update import update_mutation_factory
from .pipeline.factories.delete import delete_mutation_factory


class MutationGenerator:
    """Creates GraphQL mutations for Django models using pipeline architecture."""

    def __init__(
        self,
        type_generator: TypeGenerator,
        settings: Optional[MutationGeneratorSettings] = None,
        schema_name: str = "default",
    ):
        self.type_generator = type_generator
        self.schema_name = schema_name
        self.settings = settings or MutationGeneratorSettings.from_schema(schema_name)

        # Initialize components
        self.nested_handler = NestedOperationHandler()
        self.input_validator = get_input_validator(schema_name)
        self.tenant_applicator = self._get_tenant_applicator()

        # Pipeline builder with settings
        self.pipeline_builder = PipelineBuilder(self.settings)

    def generate_create_mutation(self, model: type[models.Model]) -> type[graphene.Mutation]:
        """Generate a create mutation using pipeline factory."""
        model_type = self.type_generator.generate_object_type(model)
        input_type = self.type_generator.generate_input_type(model, mutation_type="create")
        graphql_meta = get_model_graphql_meta(model)

        return create_mutation_factory(
            model=model,
            model_type=model_type,
            input_type=input_type,
            graphql_meta=graphql_meta,
            pipeline_builder=self.pipeline_builder,
            nested_handler=self.nested_handler,
            input_validator=self.input_validator,
            tenant_applicator=self.tenant_applicator,
        )

    def generate_update_mutation(self, model: type[models.Model]) -> type[graphene.Mutation]:
        """Generate an update mutation using pipeline factory."""
        model_type = self.type_generator.generate_object_type(model)
        input_type = self.type_generator.generate_input_type(model, partial=True, mutation_type="update")
        graphql_meta = get_model_graphql_meta(model)

        return update_mutation_factory(
            model=model,
            model_type=model_type,
            input_type=input_type,
            graphql_meta=graphql_meta,
            pipeline_builder=self.pipeline_builder,
            nested_handler=self.nested_handler,
            input_validator=self.input_validator,
            tenant_applicator=self.tenant_applicator,
        )

    def generate_delete_mutation(self, model: type[models.Model]) -> type[graphene.Mutation]:
        """Generate a delete mutation using pipeline factory."""
        model_type = self.type_generator.generate_object_type(model)
        graphql_meta = get_model_graphql_meta(model)

        return delete_mutation_factory(
            model=model,
            model_type=model_type,
            graphql_meta=graphql_meta,
            pipeline_builder=self.pipeline_builder,
            tenant_applicator=self.tenant_applicator,
        )
```

### Phase 6: GraphQLMeta Integration

#### Step 6.1: Add Pipeline Customization to GraphQLMeta

**File:** `rail_django/core/meta.py` (additions)

```python
class GraphQLMeta:
    class Pipeline:
        """Configure mutation pipeline for this model."""

        # Add custom steps
        extra_steps: list[Type[MutationStep]] = []

        # Skip specific steps by name
        skip_steps: list[str] = []

        # Override step order
        step_order: dict[str, int] = {}

        # Per-operation customization
        create_steps: list[Type[MutationStep]] = []
        update_steps: list[Type[MutationStep]] = []
        delete_steps: list[Type[MutationStep]] = []
```

**Usage:**

```python
class Order(models.Model):
    class GraphQLMeta:
        pipeline = GraphQLMeta.Pipeline(
            extra_steps=[
                InventoryCheckStep,      # Custom step
                NotificationStep,
            ],
            skip_steps=["audit"],        # Skip default audit
            create_steps=[
                OrderNumberGenerationStep,
            ],
        )
```

---

## Migration Strategy

### Step 1: Parallel Implementation (Week 1)
- Create `pipeline/` directory structure
- Implement all step classes
- Implement factories
- Keep existing `mutations_crud.py` unchanged

### Step 2: Feature Flag (Week 2)
- Add setting: `RAIL_MUTATION_BACKEND = "pipeline"` or `"legacy"`
- Update `MutationGenerator` to use flag
- Run both in tests to verify parity

### Step 3: Gradual Rollout (Week 3)
- Enable pipeline for new models
- Monitor for issues
- Fix any edge cases

### Step 4: Full Migration (Week 4)
- Switch default to pipeline
- Deprecate legacy code
- Remove `mutations_crud.py`

---

## Testing Strategy

### Unit Tests for Steps

```python
# tests/unit/test_pipeline_steps.py

class TestAuthenticationStep:
    def test_allows_authenticated_user(self):
        ctx = MutationContext(...)
        ctx.info.context.user = authenticated_user

        step = AuthenticationStep()
        result = step.execute(ctx)

        assert not result.should_abort
        assert len(result.errors) == 0

    def test_blocks_anonymous_user(self):
        ctx = MutationContext(...)
        ctx.info.context.user = AnonymousUser()

        step = AuthenticationStep()
        result = step.execute(ctx)

        assert result.should_abort
        assert "Authentication required" in result.errors[0].message
```

### Integration Tests

```python
# tests/integration/test_pipeline_mutations.py

class TestCreateMutationPipeline:
    def test_full_create_flow(self, schema, authenticated_client):
        mutation = """
            mutation CreateBook($input: CreateBookInput!) {
                create_book(input: $input) {
                    ok
                    object { id title }
                    errors { field message }
                }
            }
        """
        result = authenticated_client.execute(mutation, variables={...})

        assert result["data"]["create_book"]["ok"] is True
```

---

## Benefits Summary

| Aspect | Before (Closure) | After (Pipeline) |
|--------|------------------|------------------|
| **Testability** | Must test through generator | Each step unit-testable |
| **Debugging** | Hard to trace (dynamic classes) | Clear step names in traces |
| **Customization** | Override entire mutate() | Add/remove/reorder steps |
| **Code reuse** | Duplicated across mutations | Shared step classes |
| **Dependencies** | Implicit (closures) | Explicit (class attributes) |
| **Extension** | Subclass dynamically-created class | Implement MutationStep |

---

## Open Questions

1. **Backward compatibility**: Should we support both backends forever or deprecate legacy?
2. **Step registration**: Should custom steps be registered globally or per-model?
3. **Async support**: Should steps support async execution for future compatibility?
4. **Error accumulation**: Should pipeline continue after non-critical errors or fail fast?
