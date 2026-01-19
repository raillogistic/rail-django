# Mutation Generators Improvement Plan

This document outlines the technical implementation plan to fix bugs, improve security, reduce code duplication, and enhance code quality in the Rail Django mutation generators.

---

## Table of Contents

1. [Critical Bug Fixes](#1-critical-bug-fixes)
2. [Security Hardening](#2-security-hardening)
3. [Code Deduplication](#3-code-deduplication)
4. [Exception Handling](#4-exception-handling)
5. [Test Coverage](#5-test-coverage)
6. [Implementation Order](#6-implementation-order)

---

## 1. Critical Bug Fixes

### 1.1 Fix Duplicate Reverse Relations Processing

**File:** `rail_django/generators/nested_operations.py`
**Lines:** 1741-1759

**Problem:** `_get_reverse_relations` iterates over `model._meta.related_objects` twice with identical logic.

```python
# BEFORE (duplicate iteration):
def _get_reverse_relations(self, model):
    relations = {}

    # Use the modern Django approach
    if hasattr(model._meta, "related_objects"):
        for rel in model._meta.related_objects:
            # ... process relations ...

    # For modern Django versions, use related_objects  <- DUPLICATE!
    if hasattr(model._meta, "related_objects"):
        for rel in model._meta.related_objects:
            # ... same processing again ...

    return relations

# AFTER (single iteration):
def _get_reverse_relations(self, model):
    relations = {}

    if hasattr(model._meta, "related_objects"):
        for rel in model._meta.related_objects:
            accessor_name = rel.get_accessor_name()
            if accessor_name and not accessor_name.startswith("_"):
                relations[accessor_name] = rel

    return relations
```

---

### 1.2 Fix Inconsistent Return Types

**File:** `rail_django/generators/mutations_crud.py`
**Lines:** 125 vs 489

**Problem:** CreateMutation returns `errors=None` on success while UpdateMutation returns `errors=[]`.

```python
# BEFORE (inconsistent):
# CreateMutation (line 125):
return cls(ok=True, object=instance, errors=None)

# UpdateMutation (line 489):
return UpdateMutation(ok=True, object=instance, errors=[])

# AFTER (consistent):
# Both mutations:
return cls(ok=True, object=instance, errors=[])
```

---

### 1.3 Fix Hardcoded Mandatory Fields Map

**File:** `rail_django/generators/mutations_crud.py`
**Lines:** 315-333 and 690-705

**Problem:** Mandatory fields are hardcoded in a static dictionary rather than read from model metadata.

```python
# BEFORE (hardcoded):
def _get_mandatory_fields(cls, model: type[models.Model]) -> list[str]:
    mandatory_fields_map = {
        "BlogPost": ["category"],
        # Add other models and their mandatory fields here
    }
    model_name = model.__name__
    return mandatory_fields_map.get(model_name, [])

# AFTER (dynamic from model):
def _get_mandatory_fields(cls, model: type[models.Model]) -> list[str]:
    """Get mandatory fields from model metadata or GraphQLMeta."""
    mandatory = []

    # Check GraphQLMeta first
    graphql_meta = get_model_graphql_meta(model)
    if hasattr(graphql_meta, "mandatory_fields"):
        return list(graphql_meta.mandatory_fields)

    # Fall back to model field definitions
    for field in model._meta.get_fields():
        if hasattr(field, "blank") and hasattr(field, "null"):
            if not field.blank and not field.null and not field.has_default():
                if field.name not in ("id", "pk"):
                    mandatory.append(field.name)

    return mandatory
```

---

### 1.4 Fix GraphQL Global ID Decoding Error Handling

**File:** `rail_django/generators/mutations_crud.py`
**Lines:** 443-454

**Problem:** When GraphQL ID decoding fails, the code falls back to trying the original ID again, producing a confusing duplicate error.

```python
# BEFORE (confusing fallback):
try:
    decoded_type, decoded_id = from_global_id(record_id)
    # ...
except Exception:
    # If all else fails, raise the original error
    scoped = self._apply_tenant_scope(...)
    instance = scoped.get(pk=record_id)  # Will fail again!

# AFTER (clear error):
try:
    decoded_type, decoded_id = from_global_id(record_id)
    if decoded_type and decoded_id:
        scoped = self._apply_tenant_scope(...)
        instance = scoped.get(pk=decoded_id)
    else:
        raise ValueError("Invalid global ID format")
except Exception as decode_error:
    # Try as raw ID
    try:
        scoped = self._apply_tenant_scope(...)
        instance = scoped.get(pk=record_id)
    except model.DoesNotExist:
        raise model.DoesNotExist(
            f"{model.__name__} with id '{record_id}' not found. "
            f"If using Relay global IDs, ensure the ID format is correct."
        )
```

---

### 1.5 Fix Potential Memory Leak in NestedOperationHandler

**File:** `rail_django/generators/nested_operations.py`
**Lines:** 50-51

**Problem:** `_processed_objects` and `_validation_errors` accumulate if handler is reused.

```python
# BEFORE (potential accumulation):
def __init__(self, mutation_settings=None, schema_name: str = "default"):
    self._processed_objects: set[str] = set()
    self._validation_errors: list[str] = []

# AFTER (clear on each operation):
def __init__(self, mutation_settings=None, schema_name: str = "default"):
    self._processed_objects: set[str] = set()
    self._validation_errors: list[str] = []

def _reset_state(self) -> None:
    """Reset internal state before each operation."""
    self._processed_objects.clear()
    self._validation_errors.clear()

def handle_nested_create(self, model, input_data, ...):
    self._reset_state()  # Clear state at start
    # ... rest of implementation
```

---

### 1.6 Fix Loop Variable Reassignment in Bulk Operations

**File:** `rail_django/generators/mutations_bulk.py`
**Lines:** 68-69

**Problem:** Loop variable `input_data` is reassigned inside the loop, which is confusing.

```python
# BEFORE (confusing reassignment):
for input_data in inputs:
    input_data = cls._normalize_enum_inputs(input_data, model)  # Reassignment!
    input_data = self._apply_tenant_input(...)

# AFTER (clear variable names):
for raw_input in inputs:
    normalized_input = cls._normalize_enum_inputs(raw_input, model)
    processed_input = self._apply_tenant_input(normalized_input, ...)
```

---

### 1.7 Fix Orphaned Deleted Instances on Permission Failure

**File:** `rail_django/generators/mutations_bulk.py`
**Lines:** 356-372

**Problem:** Permission checks happen after storing instances, causing partial state on failure.

```python
# BEFORE (permission check after storage):
deleted_instances = list(instances)
for inst in deleted_instances:
    graphql_meta.ensure_operation_access(...)  # May raise

for inst in deleted_instances:
    audited_delete(info, inst)  # Partial deletion possible

# AFTER (all checks before any deletion):
instances_list = list(instances)

# Phase 1: All permission checks
for inst in instances_list:
    graphql_meta.ensure_operation_access("delete", info=info, instance=inst)

# Phase 2: All deletions (only if all checks pass)
deleted_instances = []
for inst in instances_list:
    audited_delete(info, inst)
    deleted_instances.append(inst)
```

---

### 1.8 Fix Inconsistent ID Type Handling

**File:** `rail_django/generators/nested_operations.py`
**Lines:** 946-948 vs 1068-1070

**Problem:** Inconsistent type handling when tracking updated object IDs.

```python
# BEFORE (inconsistent):
updated_object_ids.add(int(item["id"]))  # Forced to int
# ...
updated_object_ids.add(pk_val)  # Keeps original type

# AFTER (consistent normalization):
def _normalize_pk(self, pk_value) -> str:
    """Normalize PK to string for consistent comparison."""
    return str(pk_value)

# Usage:
updated_object_ids.add(self._normalize_pk(item["id"]))
updated_object_ids.add(self._normalize_pk(pk_val))
```

---

### 1.9 Fix French Error Messages

**File:** `rail_django/generators/mutations_crud.py`
**Lines:** 401-404

**Problem:** French error messages in English codebase.

```python
# BEFORE (French):
message="L'identifiant est requis pour la mise à jour."

# AFTER (English with i18n support):
from django.utils.translation import gettext_lazy as _

ERROR_ID_REQUIRED_FOR_UPDATE = _("ID is required for update operations.")
ERROR_DUPLICATE_VALUE = _("Duplicate value: field '{field}' already exists.")
ERROR_FIELD_REQUIRED = _("Field '{field}' cannot be null.")

# Usage:
message=str(ERROR_ID_REQUIRED_FOR_UPDATE)
```

---

## 2. Security Hardening

### 2.1 Add Bulk Operation Size Limits

**File:** `rail_django/generators/mutations_bulk.py`
**Lines:** 50-51

**Problem:** No limit on the number of items in bulk operations.

```python
# BEFORE (no limit):
def mutate(cls, root, info, inputs: list[dict]) -> "BulkCreateMutation":
    # No check for len(inputs) > max_bulk_size

# AFTER (with limit):
DEFAULT_MAX_BULK_SIZE = 100

@classmethod
def mutate(cls, root, info, inputs: list[dict]) -> "BulkCreateMutation":
    max_bulk_size = getattr(
        cls._mutation_settings, "max_bulk_size", DEFAULT_MAX_BULK_SIZE
    )

    if len(inputs) > max_bulk_size:
        return cls(
            ok=False,
            objects=[],
            errors=[
                build_mutation_error(
                    message=f"Bulk operation exceeds maximum size of {max_bulk_size} items."
                )
            ],
        )
    # ... rest of implementation
```

---

### 2.2 Add Nested Operation Depth Limiting

**File:** `rail_django/generators/nested_operations.py`
**Lines:** 274-667

**Problem:** `max_depth` is defined but not enforced during recursive calls.

```python
# BEFORE (no enforcement):
def handle_nested_create(
    self,
    model: type[models.Model],
    input_data: dict[str, Any],
    parent_instance: Optional[models.Model] = None,
    info: Optional[graphene.ResolveInfo] = None,
) -> models.Model:
    # No depth tracking!

# AFTER (with depth enforcement):
class NestedDepthError(ValueError):
    """Raised when nested operation exceeds maximum depth."""
    pass

def handle_nested_create(
    self,
    model: type[models.Model],
    input_data: dict[str, Any],
    parent_instance: Optional[models.Model] = None,
    info: Optional[graphene.ResolveInfo] = None,
    current_depth: int = 0,
) -> models.Model:
    if current_depth > self.max_depth:
        raise NestedDepthError(
            f"Nested operation exceeds maximum depth of {self.max_depth}. "
            f"Current depth: {current_depth}"
        )

    # ... existing logic ...

    # Recursive calls pass incremented depth:
    nested_instance = self.handle_nested_create(
        related_model,
        nested_data,
        instance,
        info,
        current_depth=current_depth + 1,
    )
```

---

### 2.3 Add Input Sanitization to Bulk Operations

**File:** `rail_django/generators/mutations_bulk.py`
**Lines:** 47-79

**Problem:** Bulk create doesn't call `_sanitize_input_data` like single create does.

```python
# BEFORE (no sanitization):
for raw_input in inputs:
    normalized_input = cls._normalize_enum_inputs(raw_input, model)
    # Missing sanitization!

# AFTER (with sanitization):
for raw_input in inputs:
    sanitized_input = cls._sanitize_input_data(raw_input)
    normalized_input = cls._normalize_enum_inputs(sanitized_input, model)
```

---

### 2.4 Sanitize Exception Messages

**File:** `rail_django/generators/mutations_crud.py`
**Lines:** 140-147, 511-518

**Problem:** Raw exception messages are exposed to users.

```python
# BEFORE (leaks internal details):
except Exception as exc:
    error_objects = [
        build_mutation_error(
            message=f"Failed to create {model_name}: {str(exc)}"  # Exposes internal error!
        )
    ]

# AFTER (sanitized):
import logging
logger = logging.getLogger(__name__)

def _sanitize_error_message(exc: Exception, operation: str, model_name: str) -> str:
    """Return user-safe error message while logging full details."""
    logger.exception(f"Mutation error during {operation} on {model_name}")

    # Known safe exceptions
    if isinstance(exc, ValidationError):
        return str(exc)
    if isinstance(exc, PermissionDenied):
        return str(exc)

    # Generic message for unknown errors
    return f"An error occurred while processing {operation} for {model_name}."

# Usage:
except Exception as exc:
    transaction.set_rollback(True)
    error_objects = [
        build_mutation_error(
            message=_sanitize_error_message(exc, "create", model_name)
        )
    ]
```

---

### 2.5 Add Authorization Check Before Cascade Delete

**File:** `rail_django/generators/nested_operations.py`
**Lines:** 1439-1509

**Problem:** `handle_cascade_delete` doesn't verify authorization for related objects.

```python
# BEFORE (no auth check):
def handle_cascade_delete(self, instance, cascade_rules=None):
    for related_obj in related_objects:
        # ... directly deletes without auth check

# AFTER (with auth check):
def handle_cascade_delete(
    self,
    instance: models.Model,
    cascade_rules: Optional[dict[str, str]] = None,
    info: Optional[graphene.ResolveInfo] = None,
) -> list[str]:
    deleted_ids = []

    for related_obj in related_objects:
        # Verify permission for each related object
        if info:
            related_meta = get_model_graphql_meta(type(related_obj))
            related_meta.ensure_operation_access(
                "delete", info=info, instance=related_obj
            )

        # Also verify tenant access
        if info:
            self._enforce_tenant_access(
                related_obj, info, type(related_obj), operation="delete"
            )

        # Now safe to delete
        related_obj.delete()
        deleted_ids.append(str(related_obj.pk))

    return deleted_ids
```

---

### 2.6 Add Depth Limit to validate_nested_data

**File:** `rail_django/generators/nested_operations.py`
**Lines:** 1511-1568

**Problem:** `validate_nested_data` checks circular refs but not depth limits.

```python
# BEFORE (no depth check):
def validate_nested_data(
    self,
    model: type[models.Model],
    input_data: dict[str, Any],
    operation: str = "create",
) -> list[str]:
    # Checks circular refs but NOT depth!

# AFTER (with depth check):
def validate_nested_data(
    self,
    model: type[models.Model],
    input_data: dict[str, Any],
    operation: str = "create",
    current_depth: int = 0,
) -> list[str]:
    errors = []

    # Check depth limit
    if current_depth > self.max_depth:
        errors.append(
            f"Nested data exceeds maximum depth of {self.max_depth}"
        )
        return errors  # Don't recurse further

    # ... existing circular reference checks ...

    # Recursive validation with depth tracking
    for field_name, field_data in input_data.items():
        if isinstance(field_data, dict):
            errors.extend(
                self.validate_nested_data(
                    related_model,
                    field_data,
                    operation,
                    current_depth=current_depth + 1,
                )
            )

    return errors
```

---

### 2.7 Stricter ID Format Validation

**File:** `rail_django/generators/nested_operations.py`
**Lines:** 371-376, 438-442

**Problem:** Permissive ID coercion could allow unexpected values.

```python
# BEFORE (permissive):
if isinstance(value, str) and value.isdigit():
    try:
        pk_value = int(value)
    except (TypeError, ValueError):
        pass  # Silently keeps original value

# AFTER (strict validation):
def _validate_and_normalize_pk(self, value: Any, field_name: str) -> Any:
    """Validate and normalize a primary key value."""
    if value is None:
        return None

    # Already an integer
    if isinstance(value, int):
        return value

    # UUID string
    if isinstance(value, str):
        # Check if it's a valid UUID
        try:
            import uuid
            uuid.UUID(value)
            return value  # Keep as string for UUID fields
        except ValueError:
            pass

        # Check if it's a numeric ID
        if value.isdigit():
            return int(value)

        # Check if it's a Relay global ID
        try:
            from graphql_relay import from_global_id
            type_name, decoded_id = from_global_id(value)
            if decoded_id:
                return int(decoded_id) if decoded_id.isdigit() else decoded_id
        except Exception:
            pass

    raise ValueError(
        f"Invalid ID format for field '{field_name}': {value!r}"
    )
```

---

## 3. Code Deduplication

### 3.1 Create Shared Mutation Utilities Module

**New File:** `rail_django/generators/mutations_utils.py`

Extract common utility functions used across all mutation types.

```python
"""
Shared utilities for mutation generators.
"""
import logging
from typing import Any, Dict, List, Type

from django.db import models
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


def sanitize_input_data(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize input data for safe processing.

    - Converts non-string IDs to strings
    - Strips whitespace from string values
    - Removes None values (optional based on config)
    """
    if not input_data:
        return {}

    sanitized = {}
    for key, value in input_data.items():
        if key == "id" and value is not None:
            sanitized[key] = str(value)
        elif isinstance(value, str):
            sanitized[key] = value.strip()
        elif isinstance(value, dict):
            sanitized[key] = sanitize_input_data(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_input_data(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


def normalize_enum_inputs(
    input_data: Dict[str, Any],
    model: Type[models.Model],
) -> Dict[str, Any]:
    """
    Normalize GraphQL enum values to Django model values.
    """
    if not input_data:
        return {}

    normalized = dict(input_data)

    for field in model._meta.get_fields():
        if not hasattr(field, "choices") or not field.choices:
            continue

        field_name = field.name
        if field_name not in normalized:
            continue

        value = normalized[field_name]
        if value is None:
            continue

        # Handle Graphene Enum objects
        if hasattr(value, "value"):
            normalized[field_name] = value.value
        elif hasattr(value, "name"):
            # Map enum name to choice value
            choice_map = {str(choice[0]).upper(): choice[0] for choice in field.choices}
            normalized[field_name] = choice_map.get(str(value).upper(), value)

    return normalized


def get_mandatory_fields(model: Type[models.Model]) -> List[str]:
    """
    Get mandatory fields from model metadata or field definitions.
    """
    from ..core.meta import get_model_graphql_meta

    # Check GraphQLMeta first
    graphql_meta = get_model_graphql_meta(model)
    if hasattr(graphql_meta, "mandatory_fields"):
        return list(graphql_meta.mandatory_fields)

    # Fall back to model field definitions
    mandatory = []
    for field in model._meta.get_fields():
        if not hasattr(field, "blank") or not hasattr(field, "null"):
            continue
        if field.name in ("id", "pk"):
            continue
        if hasattr(field, "primary_key") and field.primary_key:
            continue

        has_default = (
            hasattr(field, "default") and field.default is not models.NOT_PROVIDED
        ) or (hasattr(field, "has_default") and field.has_default())

        if not field.blank and not field.null and not has_default:
            mandatory.append(field.name)

    return mandatory


def normalize_pk(pk_value: Any) -> str:
    """Normalize PK to string for consistent comparison."""
    if pk_value is None:
        return ""
    return str(pk_value)


def sanitize_error_message(
    exc: Exception,
    operation: str,
    model_name: str,
) -> str:
    """Return user-safe error message while logging full details."""
    from django.core.exceptions import PermissionDenied

    logger.exception(
        f"Mutation error during {operation} on {model_name}",
        extra={"model": model_name, "operation": operation},
    )

    # Known safe exceptions - return their message
    if isinstance(exc, ValidationError):
        return str(exc)
    if isinstance(exc, PermissionDenied):
        return str(exc)

    # Generic message for unknown errors
    return f"An error occurred while processing {operation}."
```

---

### 3.2 Create Tenant/Permission Mixin

**New File:** `rail_django/generators/mutations_base.py`

Extract shared tenant and permission logic.

```python
"""
Base classes and mixins for mutation generators.
"""
import logging
from typing import Any, Optional, Type

from django.db import models
import graphene

from ..core.meta import get_model_graphql_meta

logger = logging.getLogger(__name__)


class TenantMixin:
    """Mixin providing tenant-scoped operations."""

    def _apply_tenant_scope(
        self,
        queryset: models.QuerySet,
        info: graphene.ResolveInfo,
        model: Type[models.Model],
        operation: str = "list",
    ) -> models.QuerySet:
        """Apply tenant scope to queryset."""
        try:
            from ..extensions.multitenancy import apply_tenant_queryset
            return apply_tenant_queryset(queryset, info, model, operation)
        except ImportError:
            logger.debug("Multitenancy extension not available")
            return queryset
        except Exception as e:
            logger.warning(f"Failed to apply tenant scope: {e}")
            return queryset

    def _enforce_tenant_access(
        self,
        instance: models.Model,
        info: graphene.ResolveInfo,
        model: Type[models.Model],
        operation: str = "retrieve",
    ) -> None:
        """Verify instance belongs to current tenant."""
        try:
            from ..extensions.multitenancy import enforce_tenant_access
            enforce_tenant_access(instance, info, model, operation)
        except ImportError:
            pass  # Multitenancy not enabled
        except Exception as e:
            logger.warning(f"Tenant access check failed: {e}")
            raise

    def _apply_tenant_input(
        self,
        input_data: dict,
        info: graphene.ResolveInfo,
        model: Type[models.Model],
    ) -> dict:
        """Apply tenant context to input data."""
        try:
            from ..extensions.multitenancy import apply_tenant_input
            return apply_tenant_input(input_data, info, model)
        except ImportError:
            return input_data
        except Exception as e:
            logger.warning(f"Failed to apply tenant input: {e}")
            return input_data


class PermissionMixin:
    """Mixin providing permission checking operations."""

    def _has_operation_guard(
        self,
        graphql_meta: Any,
        operation: str,
    ) -> bool:
        """Check if operation has a guard defined."""
        if not graphql_meta:
            return False

        guards = getattr(graphql_meta, "operation_guards", None)
        if not guards:
            return False

        return operation in guards

    def _build_model_permission_name(
        self,
        model: Type[models.Model],
        operation: str,
    ) -> str:
        """Build permission name for model operation."""
        app_label = model._meta.app_label
        model_name = model._meta.model_name

        operation_map = {
            "create": "add",
            "retrieve": "view",
            "update": "change",
            "delete": "delete",
            "list": "view",
        }

        perm_op = operation_map.get(operation, operation)
        return f"{app_label}.{perm_op}_{model_name}"

    def _enforce_model_permission(
        self,
        info: graphene.ResolveInfo,
        model: Type[models.Model],
        operation: str,
        graphql_meta: Optional[Any] = None,
    ) -> None:
        """Enforce model-level permission for operation."""
        if graphql_meta is None:
            graphql_meta = get_model_graphql_meta(model)

        # Check if operation has a guard (overrides permission)
        if self._has_operation_guard(graphql_meta, operation):
            return  # Guard will handle authorization

        # Check require_authentication
        if getattr(graphql_meta, "require_authentication", False):
            user = getattr(info.context, "user", None)
            if not user or not getattr(user, "is_authenticated", False):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("Authentication required")

        # Check model permission
        permission = self._build_model_permission_name(model, operation)
        user = getattr(info.context, "user", None)

        if user and hasattr(user, "has_perm"):
            if not user.has_perm(permission):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied(f"Permission denied: {permission}")


class MutationGeneratorBase(TenantMixin, PermissionMixin):
    """Base class for mutation generators with common functionality."""

    def __init__(self, schema_name: str = "default"):
        self.schema_name = schema_name

    def _get_nested_handler(
        self,
        info: graphene.ResolveInfo,
    ):
        """Get or create nested operation handler."""
        from .nested_operations import NestedOperationHandler

        if hasattr(info.context, "mutation_generator"):
            handler = getattr(info.context.mutation_generator, "nested_handler", None)
            if handler:
                return handler

        return NestedOperationHandler(schema_name=self.schema_name)
```

---

### 3.3 Refactor Mutations to Use Shared Code

Update `mutations_crud.py` to use shared utilities:

```python
# BEFORE (duplicated in each class):
class CreateMutation:
    @classmethod
    def _sanitize_input_data(cls, input_data):
        # ... 25 lines of code ...

    @classmethod
    def _normalize_enum_inputs(cls, input_data, model):
        # ... 40 lines of code ...

    @classmethod
    def _get_mandatory_fields(cls, model):
        # ... 20 lines of code ...

class UpdateMutation:
    @classmethod
    def _sanitize_input_data(cls, input_data):
        # ... same 25 lines of code ...

    # ... etc ...

# AFTER (using shared utilities):
from .mutations_utils import (
    sanitize_input_data,
    normalize_enum_inputs,
    get_mandatory_fields,
    sanitize_error_message,
)
from .mutations_base import MutationGeneratorBase

class CreateMutation:
    @classmethod
    def mutate(cls, root, info, input):
        input = sanitize_input_data(input)
        input = normalize_enum_inputs(input, model)
        mandatory = get_mandatory_fields(model)
        # ...
```

---

### 3.4 Create Shared Audit Wrapper

**File:** `rail_django/generators/mutations_utils.py` (add to existing)

```python
def wrap_with_audit(
    model: Type[models.Model],
    operation: str,
    func: callable,
) -> callable:
    """
    Wrap a function with audit logging if available.

    Returns the original function if audit logging is not configured.
    """
    try:
        from ..security.audit_logging import audit_data_modification

        def audited_func(info, instance, *args, **kwargs):
            result = func(info, instance, *args, **kwargs)
            audit_data_modification(
                info=info,
                model=model,
                operation=operation,
                instance=result or instance,
            )
            return result

        return audited_func

    except ImportError:
        logger.debug("Audit logging not available")
        return func
    except Exception as e:
        logger.warning(f"Failed to setup audit wrapper: {e}")
        return func
```

---

### 3.5 Extract FK Resolution Helper

**File:** `rail_django/generators/mutations_utils.py` (add to existing)

```python
def resolve_fk_id(
    value: Any,
    related_model: Type[models.Model],
    queryset: Optional[models.QuerySet] = None,
    field_name: str = "id",
) -> Optional[models.Model]:
    """
    Resolve a foreign key ID to its related object.

    Handles string IDs, integer IDs, and Relay global IDs.
    """
    if value is None:
        return None

    # Normalize to appropriate type
    pk_value = value
    if isinstance(value, str):
        if value.isdigit():
            pk_value = int(value)
        else:
            # Try Relay global ID
            try:
                from graphql_relay import from_global_id
                type_name, decoded_id = from_global_id(value)
                if decoded_id:
                    pk_value = int(decoded_id) if decoded_id.isdigit() else decoded_id
            except Exception:
                pass  # Keep original value

    # Get queryset
    if queryset is None:
        queryset = related_model.objects.all()

    try:
        return queryset.get(pk=pk_value)
    except related_model.DoesNotExist:
        raise ValueError(
            f"{related_model.__name__} with {field_name}='{value}' not found"
        )
```

---

## 4. Exception Handling

### 4.1 Replace Bare Except Clauses

**Files:** Multiple locations

```python
# BEFORE (bare except):
try:
    field = model._meta.get_field(field_name)
except:
    continue

# AFTER (specific exceptions):
from django.core.exceptions import FieldDoesNotExist

try:
    field = model._meta.get_field(field_name)
except FieldDoesNotExist:
    # Field doesn't exist on model - check for property
    if hasattr(model, field_name):
        continue
    logger.debug(f"Unknown field {field_name} on {model.__name__}")
    continue
except Exception as e:
    logger.warning(
        f"Unexpected error getting field {field_name}: {e}",
        extra={"model": model.__name__, "field": field_name},
    )
    continue
```

---

### 4.2 Fix Silent Import Failures

**File:** `rail_django/generators/mutations.py`

```python
# BEFORE (silent failure):
try:
    from ..extensions.multitenancy import apply_tenant_queryset
except Exception:
    return queryset  # Silently returns unfiltered queryset!

# AFTER (logged failure):
try:
    from ..extensions.multitenancy import apply_tenant_queryset
except ImportError:
    # Multitenancy not installed - this is expected
    return queryset
except Exception as e:
    logger.error(
        f"Unexpected error importing multitenancy: {e}",
        exc_info=True,
    )
    # In production, fail closed - return empty queryset
    if not settings.DEBUG:
        return queryset.none()
    return queryset
```

---

### 4.3 Remove Redundant ValidationError Re-raises

**File:** `rail_django/generators/nested_operations.py`

```python
# BEFORE (redundant):
try:
    # ... processing ...
except ValidationError as e:
    # Preserve field-specific errors so mutation can map them to fields
    raise e  # Redundant

# AFTER (just don't catch it):
# Don't catch ValidationError - let it propagate naturally
# ... processing ...
```

---

### 4.4 Create Custom Mutation Exceptions

**New File:** `rail_django/generators/mutations_exceptions.py`

```python
"""
Custom exceptions for mutation operations.
"""


class MutationError(Exception):
    """Base exception for mutation operations."""

    def __init__(self, message: str, field: str = None, code: str = None):
        super().__init__(message)
        self.field = field
        self.code = code


class NestedDepthError(MutationError):
    """Raised when nested operation exceeds maximum depth."""

    def __init__(self, max_depth: int, current_depth: int):
        super().__init__(
            f"Nested operation exceeds maximum depth of {max_depth}. "
            f"Current depth: {current_depth}",
            code="DEPTH_EXCEEDED",
        )
        self.max_depth = max_depth
        self.current_depth = current_depth


class BulkSizeError(MutationError):
    """Raised when bulk operation exceeds maximum size."""

    def __init__(self, max_size: int, actual_size: int):
        super().__init__(
            f"Bulk operation exceeds maximum size of {max_size} items. "
            f"Received: {actual_size}",
            code="BULK_SIZE_EXCEEDED",
        )
        self.max_size = max_size
        self.actual_size = actual_size


class CircularReferenceError(MutationError):
    """Raised when circular reference is detected in nested data."""

    def __init__(self, model_name: str, path: str):
        super().__init__(
            f"Circular reference detected in nested data for {model_name}. Path: {path}",
            code="CIRCULAR_REFERENCE",
        )
        self.model_name = model_name
        self.path = path


class TenantAccessError(MutationError):
    """Raised when tenant access is denied."""

    def __init__(self, model_name: str, operation: str):
        super().__init__(
            f"Tenant access denied for {operation} on {model_name}",
            code="TENANT_ACCESS_DENIED",
        )
        self.model_name = model_name
        self.operation = operation
```

---

## 5. Test Coverage

### 5.1 Create Bulk Operations Tests

**New File:** `rail_django/tests/unit/test_mutations_bulk.py`

```python
"""
Unit tests for bulk mutation operations.
"""
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.unit


class TestBulkCreateMutation:
    """Tests for BulkCreateMutation."""

    def test_bulk_create_respects_size_limit(self):
        """Bulk create should reject inputs exceeding max size."""
        # TODO: Implement
        pass

    def test_bulk_create_applies_sanitization(self):
        """Bulk create should sanitize all inputs."""
        # TODO: Implement
        pass

    def test_bulk_create_normalizes_enums(self):
        """Bulk create should normalize enum values."""
        # TODO: Implement
        pass

    def test_bulk_create_atomic_rollback(self):
        """Bulk create should rollback all on any failure."""
        # TODO: Implement
        pass

    def test_bulk_create_permission_check(self):
        """Bulk create should check permissions for all items."""
        # TODO: Implement
        pass


class TestBulkUpdateMutation:
    """Tests for BulkUpdateMutation."""

    def test_bulk_update_respects_size_limit(self):
        """Bulk update should reject inputs exceeding max size."""
        pass

    def test_bulk_update_tenant_isolation(self):
        """Bulk update should respect tenant boundaries."""
        pass


class TestBulkDeleteMutation:
    """Tests for BulkDeleteMutation."""

    def test_bulk_delete_permission_before_delete(self):
        """All permission checks should happen before any deletion."""
        pass

    def test_bulk_delete_cascade_authorization(self):
        """Cascade deletes should check authorization for related objects."""
        pass
```

---

### 5.2 Create Nested Operations Tests

**New File:** `rail_django/tests/unit/test_nested_operations.py`

```python
"""
Unit tests for nested mutation operations.
"""
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.unit


class TestNestedOperationHandler:
    """Tests for NestedOperationHandler."""

    def test_depth_limit_enforcement(self):
        """Nested operations should enforce depth limits."""
        from rail_django.generators.nested_operations import NestedOperationHandler
        from rail_django.generators.mutations_exceptions import NestedDepthError

        handler = NestedOperationHandler()
        handler.max_depth = 3

        # Build deeply nested data
        deep_data = {"level1": {"level2": {"level3": {"level4": {}}}}}

        # Should raise NestedDepthError
        # TODO: Implement test
        pass

    def test_circular_reference_detection(self):
        """Nested operations should detect circular references."""
        pass

    def test_state_reset_between_operations(self):
        """Handler state should reset between operations."""
        pass

    def test_cascade_delete_authorization(self):
        """Cascade delete should check authorization for each object."""
        pass

    def test_tenant_isolation_in_nested_create(self):
        """Nested create should respect tenant boundaries."""
        pass

    def test_fk_resolution_with_global_id(self):
        """FK resolution should handle Relay global IDs."""
        pass

    def test_fk_resolution_with_invalid_id(self):
        """FK resolution should fail clearly on invalid IDs."""
        pass


class TestNestedValidation:
    """Tests for nested data validation."""

    def test_validate_nested_data_depth_limit(self):
        """Validation should reject data exceeding depth limit."""
        pass

    def test_validate_nested_data_circular_ref(self):
        """Validation should detect circular references."""
        pass
```

---

### 5.3 Create Method Mutations Tests

**New File:** `rail_django/tests/unit/test_mutations_methods.py`

```python
"""
Unit tests for method-based mutations.
"""
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.unit


class TestMethodMutation:
    """Tests for method mutation generation."""

    def test_method_with_typed_parameters(self):
        """Method mutations should respect parameter types."""
        pass

    def test_method_with_return_type(self):
        """Method mutations should handle return types."""
        pass

    def test_method_atomic_execution(self):
        """Atomic methods should rollback on failure."""
        pass

    def test_method_non_atomic_execution(self):
        """Non-atomic methods should not use transactions."""
        pass

    def test_method_permission_check(self):
        """Method mutations should check permissions."""
        pass

    def test_method_audit_logging(self):
        """Method mutations should log to audit trail."""
        pass
```

---

### 5.4 Create Mutation Security Tests

**New File:** `rail_django/tests/unit/test_mutations_security.py`

```python
"""
Unit tests for mutation security features.
"""
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.unit


class TestBulkSizeLimiting:
    """Tests for bulk operation size limits."""

    def test_create_exceeds_limit(self):
        """Bulk create should reject oversized input."""
        pass

    def test_update_exceeds_limit(self):
        """Bulk update should reject oversized input."""
        pass

    def test_delete_exceeds_limit(self):
        """Bulk delete should reject oversized input."""
        pass

    def test_custom_limit_respected(self):
        """Custom size limits should be respected."""
        pass


class TestNestedDepthLimiting:
    """Tests for nested operation depth limits."""

    def test_create_exceeds_depth(self):
        """Nested create should reject deep nesting."""
        pass

    def test_update_exceeds_depth(self):
        """Nested update should reject deep nesting."""
        pass

    def test_validation_exceeds_depth(self):
        """Validation should reject deep nesting."""
        pass


class TestErrorMessageSanitization:
    """Tests for error message sanitization."""

    def test_internal_error_hidden(self):
        """Internal errors should not leak to users."""
        pass

    def test_validation_error_shown(self):
        """Validation errors should be shown to users."""
        pass

    def test_permission_error_shown(self):
        """Permission errors should be shown to users."""
        pass


class TestTenantIsolation:
    """Tests for tenant isolation in mutations."""

    def test_create_applies_tenant(self):
        """Create should apply tenant context."""
        pass

    def test_update_verifies_tenant(self):
        """Update should verify tenant access."""
        pass

    def test_delete_verifies_tenant(self):
        """Delete should verify tenant access."""
        pass

    def test_nested_respects_tenant(self):
        """Nested operations should respect tenant boundaries."""
        pass

    def test_cascade_delete_tenant_check(self):
        """Cascade delete should check tenant for related objects."""
        pass
```

---

## 6. Implementation Order

### Phase 1: Critical Bug Fixes (Immediate) ⏳ PENDING

1. ⏳ Fix duplicate reverse relations processing (1.1)
2. ⏳ Fix inconsistent return types (1.2)
3. ⏳ Fix GraphQL ID decoding error handling (1.4)
4. ⏳ Fix memory leak in NestedOperationHandler (1.5)
5. ⏳ Fix orphaned deleted instances (1.7)

**Estimated items:** 5

---

### Phase 2: Security Hardening (High Priority) ⏳ PENDING

6. ⏳ Add bulk operation size limits (2.1)
7. ⏳ Add nested operation depth limiting (2.2)
8. ⏳ Add input sanitization to bulk operations (2.3)
9. ⏳ Sanitize exception messages (2.4)
10. ⏳ Add authorization check before cascade delete (2.5)
11. ⏳ Add depth limit to validate_nested_data (2.6)

**Estimated items:** 6

---

### Phase 3: Code Deduplication (Medium Priority) ⏳ PENDING

12. ⏳ Create mutations_utils.py with shared functions (3.1)
13. ⏳ Create mutations_base.py with TenantMixin/PermissionMixin (3.2)
14. ⏳ Refactor mutations_crud.py to use shared code (3.3)
15. ⏳ Refactor mutations_bulk.py to use shared code
16. ⏳ Refactor nested_operations.py to use shared code
17. ⏳ Create shared audit wrapper (3.4)
18. ⏳ Extract FK resolution helper (3.5)

**Estimated items:** 7

---

### Phase 4: Exception Handling (Medium Priority) ⏳ PENDING

19. ⏳ Create mutations_exceptions.py (4.4)
20. ⏳ Replace bare except clauses (4.1)
21. ⏳ Fix silent import failures (4.2)
22. ⏳ Remove redundant ValidationError re-raises (4.3)
23. ⏳ Fix French error messages (1.9)

**Estimated items:** 5

---

### Phase 5: Test Coverage (Medium Priority) ⏳ PENDING

24. ⏳ Create test_mutations_bulk.py (5.1)
25. ⏳ Create test_nested_operations.py (5.2)
26. ⏳ Create test_mutations_methods.py (5.3)
27. ⏳ Create test_mutations_security.py (5.4)

**Estimated items:** 4

---

### Phase 6: Code Quality (Lower Priority) ⏳ PENDING

28. ⏳ Fix hardcoded mandatory fields map (1.3)
29. ⏳ Fix loop variable reassignment (1.6)
30. ⏳ Fix inconsistent ID type handling (1.8)
31. ⏳ Add stricter ID format validation (2.7)

**Estimated items:** 4

---

## Testing Checklist

After implementing fixes, verify:

- [ ] Bulk operations respect size limits
- [ ] Nested operations enforce depth limits
- [ ] Input sanitization applied to all mutation types
- [ ] Error messages don't leak internal details
- [ ] Cascade delete checks authorization for related objects
- [ ] All permission checks happen before any modifications
- [ ] Transaction rollback works correctly on failures
- [ ] Tenant isolation maintained in nested operations
- [ ] French error messages replaced with English
- [ ] Duplicate code eliminated via shared utilities

---

## Migration Notes

### Breaking Changes

None expected. All fixes maintain backward compatibility.

### Deprecations

- Direct use of duplicated utility methods (use shared imports instead)
- Hardcoded mandatory fields map (use GraphQLMeta.mandatory_fields)

### New Settings

```python
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        "max_bulk_size": 100,         # Maximum items in bulk operations
        "max_nested_depth": 10,       # Maximum nesting depth
        "sanitize_error_messages": True,  # Hide internal error details
    }
}
```

### New Files

- `rail_django/generators/mutations_utils.py` - Shared utilities
- `rail_django/generators/mutations_base.py` - Base classes and mixins
- `rail_django/generators/mutations_exceptions.py` - Custom exceptions
- `rail_django/tests/unit/test_mutations_bulk.py`
- `rail_django/tests/unit/test_nested_operations.py`
- `rail_django/tests/unit/test_mutations_methods.py`
- `rail_django/tests/unit/test_mutations_security.py`
