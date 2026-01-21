"""
Nested Operations Handler Base Module

This module provides the base class for nested operations handling with
core utility methods for authentication, tenant scoping, and field processing.
"""

import logging
import re
import uuid
from typing import Any, Optional

import graphene
from django.core.exceptions import ValidationError
from django.db import models

from ...core.error_handling import get_error_handler
from ...core.meta import get_model_graphql_meta
from ...core.services import get_query_optimizer
from ...core.security import get_authz_manager, get_input_validator
from ...core.settings import MutationGeneratorSettings

logger = logging.getLogger(__name__)


class NestedOperationHandlerBase:
    """Base class for nested operations handler providing core utility methods."""

    def __init__(self, mutation_settings=None, schema_name: str = "default"):
        """Initialize the NestedOperationHandler."""
        self._processed_objects: set[str] = set()
        self._validation_errors: list[str] = []
        self.schema_name = schema_name

        if mutation_settings is None:
            self.mutation_settings = MutationGeneratorSettings.from_schema(schema_name)
        else:
            self.mutation_settings = mutation_settings

        self.authorization_manager = get_authz_manager(schema_name)
        self.input_validator = get_input_validator(schema_name)
        self.error_handler = get_error_handler(schema_name)
        self.query_optimizer = get_query_optimizer(schema_name)
        self.circular_reference_tracker = set()
        self.max_depth = getattr(self.mutation_settings, "max_nested_depth", 10)

    def _reset_state(self) -> None:
        """Clear all tracking collections to reset handler state."""
        self._processed_objects.clear()
        self._validation_errors.clear()
        self.circular_reference_tracker.clear()

    def _should_use_nested_operations(self, model, field_name) -> bool:
        """Check if nested operations should be used for a specific field."""
        if not self.mutation_settings:
            return True
        model_name = model.__name__

        if hasattr(self.mutation_settings, "nested_field_config"):
            cfg = self.mutation_settings.nested_field_config
            if model_name in cfg and field_name in cfg[model_name]:
                return cfg[model_name][field_name]

        if hasattr(self.mutation_settings, "nested_relations_config"):
            cfg = self.mutation_settings.nested_relations_config
            if model_name in cfg:
                return cfg[model_name]

        if hasattr(self.mutation_settings, "enable_nested_relations"):
            return self.mutation_settings.enable_nested_relations
        return True

    def _ensure_operation_access(
        self, model: type[models.Model], operation: str,
        info: Optional[graphene.ResolveInfo], instance: Optional[models.Model] = None,
    ) -> None:
        """Ensure the user has access to perform the operation."""
        if info is None:
            return
        graphql_meta = get_model_graphql_meta(model)
        self._enforce_model_permission(info, model, operation, graphql_meta)
        graphql_meta.ensure_operation_access(operation, info=info, instance=instance)

    def _has_operation_guard(self, graphql_meta, operation: str) -> bool:
        """Check if an operation guard exists."""
        guards = getattr(graphql_meta, "_operation_guards", None) or {}
        return operation in guards or "*" in guards

    def _build_model_permission_name(self, model: type[models.Model], codename: str) -> str:
        """Build the full permission name for a model operation."""
        return f"{model._meta.app_label}.{codename}_{model._meta.model_name}"

    def _normalize_permission_operation(self, operation: str) -> str:
        """Normalize operation name by removing bulk_ prefix."""
        normalized = str(operation or "").strip().lower()
        return normalized[5:] if normalized.startswith("bulk_") else normalized

    def _get_permission_codename(self, operation: str) -> Optional[str]:
        """Get the permission codename for an operation."""
        normalized = self._normalize_permission_operation(operation)
        mapping = getattr(self.mutation_settings, "model_permission_codenames", None)
        if isinstance(mapping, dict):
            codename = mapping.get(operation) or mapping.get(normalized)
            if codename:
                return str(codename).strip() or None
        return None

    def _enforce_model_permission(
        self, info: graphene.ResolveInfo, model: type[models.Model],
        operation: str, graphql_meta=None,
    ) -> None:
        """Enforce model-level permissions for an operation."""
        from graphql import GraphQLError

        if not getattr(self.authorization_manager.settings, "enable_authorization", True):
            return
        if not getattr(self.mutation_settings, "require_model_permissions", True):
            return

        normalized = self._normalize_permission_operation(operation)
        if graphql_meta is not None:
            if self._has_operation_guard(graphql_meta, operation):
                return
            if normalized and self._has_operation_guard(graphql_meta, normalized):
                return

        user = getattr(getattr(info, "context", None), "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise GraphQLError("Authentication required")

        codename = self._get_permission_codename(operation)
        if not codename:
            return

        perm_name = self._build_model_permission_name(model, codename)
        has_perm = getattr(user, "has_perm", None)
        if not callable(has_perm) or not has_perm(perm_name):
            raise GraphQLError(f"Permission required: {perm_name}")

    def _save_instance(self, instance: models.Model) -> None:
        """Validate and save a model instance."""
        instance.full_clean()
        instance.save()

    def _apply_tenant_scope(
        self, queryset: models.QuerySet, info: Optional[graphene.ResolveInfo],
        model: type[models.Model], *, operation: str = "read",
    ) -> models.QuerySet:
        """Apply tenant scoping to a queryset."""
        try:
            from ...extensions.multitenancy import apply_tenant_queryset
        except Exception:
            return queryset
        return apply_tenant_queryset(
            queryset, info, model, schema_name=self.schema_name, operation=operation
        )

    def _apply_tenant_input(
        self, input_data: dict[str, Any], info: Optional[graphene.ResolveInfo],
        model: type[models.Model], *, operation: str = "create",
    ) -> dict[str, Any]:
        """Apply tenant context to input data."""
        try:
            from ...extensions.multitenancy import apply_tenant_to_input
        except Exception:
            return input_data
        return apply_tenant_to_input(
            input_data, info, model, schema_name=self.schema_name, operation=operation
        )

    def _enforce_tenant_access(
        self, instance: models.Model, info: Optional[graphene.ResolveInfo],
        model: type[models.Model], *, operation: str = "read",
    ) -> None:
        """Enforce tenant access for an instance."""
        try:
            from ...extensions.multitenancy import ensure_tenant_access
        except Exception:
            return
        ensure_tenant_access(
            instance, info, model, schema_name=self.schema_name, operation=operation
        )

    def _get_tenant_queryset(
        self, model: type[models.Model], info: Optional[graphene.ResolveInfo],
        *, operation: str = "read",
    ) -> models.QuerySet:
        """Get a queryset with tenant scoping applied."""
        return self._apply_tenant_scope(model.objects.all(), info, model, operation=operation)

    def _has_nested_payload(self, value: Any) -> bool:
        """Check if a value contains nested operation payload."""
        if isinstance(value, dict):
            if "create" in value or "update" in value:
                return True
            if "set" in value:
                sv = value.get("set")
                if isinstance(sv, dict) or (isinstance(sv, list) and any(isinstance(i, dict) for i in sv)):
                    return True
            if set(value.keys()).issubset({"connect", "disconnect", "set"}):
                return False
            return True
        if isinstance(value, list):
            return any(isinstance(item, dict) for item in value)
        return False

    def _extract_unique_constraint_fields(self, model: type[models.Model], error: Exception) -> list[str]:
        """Extract field names from unique constraint errors."""
        msg = str(error)
        fields = []
        m = re.search(r"UNIQUE constraint failed: ([\w\., ]+)", msg)
        if m:
            for col in (p.strip() for p in m.group(1).split(",")):
                col_name = col.split(".")[-1]
                fields.append(self._map_column_to_field(model, col_name) or col_name)
        if not fields:
            m2 = re.search(r"Key \(([^\)]+)\)=\(([^\)]+)\) already exists", msg)
            if m2:
                for col_name in (c.strip() for c in m2.group(1).split(",")):
                    fields.append(self._map_column_to_field(model, col_name) or col_name)
        return fields

    def _map_column_to_field(self, model: type[models.Model], column: str) -> Optional[str]:
        """Map a DB column name to the Django model field name."""
        try:
            for f in model._meta.get_fields():
                if hasattr(f, "column") and f.column == column:
                    return f.name
        except Exception:
            pass
        return None

    def _get_field_verbose_name(self, model: type[models.Model], field_name: str) -> Optional[str]:
        """Retrieve the verbose_name for a Django field."""
        try:
            field = model._meta.get_field(field_name)
            label = getattr(field, "verbose_name", None)
            return str(label) if label else None
        except Exception:
            return None

    def _get_reverse_relations(self, model: type[models.Model]) -> dict[str, Any]:
        """Get reverse relationships for a model."""
        reverse_relations = {}
        if hasattr(model._meta, "related_objects"):
            for rel in model._meta.related_objects:
                accessor = getattr(rel, "get_accessor_name", lambda: None)()
                if accessor is None:
                    accessor = rel.related_name or f"{rel.related_model._meta.model_name}_set"
                if self._should_include_reverse_field(rel):
                    reverse_relations[accessor] = rel
        elif hasattr(model._meta, "get_fields"):
            try:
                for field in model._meta.get_fields():
                    if hasattr(field, "related_model") and hasattr(field, "get_accessor_name"):
                        if self._should_include_reverse_field(field):
                            reverse_relations[field.get_accessor_name()] = field
            except AttributeError:
                pass
        return reverse_relations

    def _should_include_reverse_field(self, rel) -> bool:
        """Determine if a reverse relationship field should be included."""
        if hasattr(rel, "through") and rel.through and not rel.through._meta.auto_created:
            return False
        if hasattr(rel, "hidden") and rel.hidden:
            return False
        if hasattr(rel, "related_model") and rel.related_model._meta.abstract:
            return False
        return True

    def _process_nested_fields(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Process nested_ prefixed fields and map them to actual field names."""
        processed = {}
        for field_name, value in input_data.items():
            if field_name.startswith("nested_"):
                actual = field_name[7:]
                if actual in input_data:
                    logger.warning(f"Both '{field_name}' and '{actual}' provided. Using nested.")
                processed[actual] = value
            else:
                if f"nested_{field_name}" not in input_data:
                    processed[field_name] = value
        return processed

    def _coerce_pk(self, value: Any) -> Any:
        """Coerce a value to an appropriate primary key type."""
        if isinstance(value, str) and value.isdigit():
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
        return value

    def _handle_integrity_error(
        self, model: type[models.Model], error: Exception, operation: str = "create",
    ) -> None:
        """Handle IntegrityError and raise appropriate ValidationError."""
        error_msg = str(error)
        match = re.search(r'null value in column "(\w+)".*violates not-null constraint', error_msg)
        if match:
            col = match.group(1)
            field_name = self._map_column_to_field(model, col) or col
            label = self._get_field_verbose_name(model, field_name) or field_name
            raise ValidationError({field_name: f"Le champ '{label}' ne peut pas etre nul."})

        fields = self._extract_unique_constraint_fields(model, error)
        if fields:
            errors = {}
            for f in fields:
                label = self._get_field_verbose_name(model, f) or f
                errors[f] = f"Doublon detecte: la valeur du champ '{label}' existe deja."
            raise ValidationError(errors)

        msg = f"Echec de la {'creation' if operation == 'create' else 'mise a jour'} de {model.__name__} : {error}"
        raise ValidationError(msg)


from .create import NestedCreateMixin
from .update import NestedUpdateMixin
from .delete import NestedDeleteMixin


class NestedOperationHandler(
    NestedCreateMixin, NestedUpdateMixin, NestedDeleteMixin, NestedOperationHandlerBase
):
    """
    Handles complex nested operations for GraphQL mutations including
    nested creates, updates, and cascade operations with proper validation.
    """
    pass
