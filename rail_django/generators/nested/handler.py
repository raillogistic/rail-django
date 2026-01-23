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

    # ... (other methods same as before) ...
    def _should_use_nested_operations(self, model, field_name) -> bool:
        """Check if nested operations should be used for a specific field."""
        if not self.mutation_settings:
            return True
        model_name = model.__name__

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
        if info is None: return
        graphql_meta = get_model_graphql_meta(model)
        self._enforce_model_permission(info, model, operation, graphql_meta)
        graphql_meta.ensure_operation_access(operation, info=info, instance=instance)

    def _has_operation_guard(self, graphql_meta, operation: str) -> bool:
        guards = getattr(graphql_meta, "_operation_guards", None) or {}
        return operation in guards or "*" in guards

    def _build_model_permission_name(self, model: type[models.Model], codename: str) -> str:
        return f"{model._meta.app_label}.{codename}_{model._meta.model_name}"

    def _normalize_permission_operation(self, operation: str) -> str:
        normalized = str(operation or "").strip().lower()
        return normalized[5:] if normalized.startswith("bulk_") else normalized

    def _get_permission_codename(self, operation: str) -> Optional[str]:
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
        instance.full_clean()
        instance.save()

    def _apply_tenant_scope(
        self, queryset: models.QuerySet, info: Optional[graphene.ResolveInfo],
        model: type[models.Model], *, operation: str = "read",
    ) -> models.QuerySet:
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
        return self._apply_tenant_scope(model.objects.all(), info, model, operation=operation)

    def _has_nested_payload(self, value: Any) -> bool:
        if isinstance(value, dict):
            return any(k in value for k in ("create", "update", "connect", "disconnect", "set"))
        return False

    def _extract_unique_constraint_fields(self, model: type[models.Model], error: Exception) -> list[str]:
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
        try:
            for f in model._meta.get_fields():
                if hasattr(f, "column") and f.column == column:
                    return f.name
        except Exception:
            pass
        return None

    def _get_field_verbose_name(self, model: type[models.Model], field_name: str) -> Optional[str]:
        try:
            field = model._meta.get_field(field_name)
            label = getattr(field, "verbose_name", None)
            return str(label) if label else None
        except Exception:
            return None

    def _get_reverse_relations(self, model: type[models.Model]) -> dict[str, Any]:
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
        if hasattr(rel, "through") and rel.through and not rel.through._meta.auto_created:
            return False
        if hasattr(rel, "hidden") and rel.hidden:
            return False
        if hasattr(rel, "related_model") and rel.related_model._meta.abstract:
            return False
        return True

    def process_relation_input(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return input_data

    def _coerce_pk(self, value: Any) -> Any:
        if isinstance(value, str) and value.isdigit():
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
        return value

    def _handle_integrity_error(
        self, model: type[models.Model], error: Exception, operation: str = "create",
    ) -> None:
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

    # --- Unified Operation Handlers ---

    def handle_connect(self, instance, field_name, data, info, is_m2m, is_reverse):
        """Handle 'connect' operation."""
        model = type(instance)
        if is_m2m:
            field = model._meta.get_field(field_name)
            manager = getattr(instance, field_name)
            ids = data if isinstance(data, list) else [data]
            for item in ids:
                 pk = self._coerce_pk(item)
                 obj = self._get_tenant_queryset(field.related_model, info, operation="retrieve").get(pk=pk)
                 manager.add(obj)
        elif is_reverse:
             # Reverse relation (OneToMany): set FK on related objects
             # We need to find the related model and the FK field pointing to us
             rel = self._get_reverse_relations(model).get(field_name)
             if not rel: return
             related_model = rel.related_model
             remote_field_name = rel.field.name
             ids = data if isinstance(data, list) else [data]
             for item in ids:
                 pk = self._coerce_pk(item)
                 obj = self._get_tenant_queryset(related_model, info, operation="update").get(pk=pk)
                 setattr(obj, remote_field_name, instance)
                 self._save_instance(obj)
        else:
             # Singular FK/O2O: set the related object
             field = model._meta.get_field(field_name)
             pk = self._coerce_pk(data)
             obj = self._get_tenant_queryset(field.related_model, info, operation="retrieve").get(pk=pk)
             setattr(instance, field_name, obj)
             self._save_instance(instance)

    def handle_disconnect(self, instance, field_name, data, info, is_m2m, is_reverse):
        """Handle 'disconnect' operation."""
        model = type(instance)
        if is_m2m:
            field = model._meta.get_field(field_name)
            manager = getattr(instance, field_name)
            ids = data if isinstance(data, list) else [data]
            for item in ids:
                 pk = self._coerce_pk(item)
                 obj = self._get_tenant_queryset(field.related_model, info, operation="retrieve").get(pk=pk)
                 manager.remove(obj)
        elif is_reverse:
             rel = self._get_reverse_relations(model).get(field_name)
             if not rel: return
             related_model = rel.related_model
             remote_field_name = rel.field.name
             ids = data if isinstance(data, list) else [data]
             for item in ids:
                 pk = self._coerce_pk(item)
                 obj = self._get_tenant_queryset(related_model, info, operation="update").get(pk=pk)
                 setattr(obj, remote_field_name, None)
                 self._save_instance(obj)
        else:
             # Singular FK/O2O: set field to None (disconnect)
             # data could be boolean True or an ID to verify
             setattr(instance, field_name, None)
             self._save_instance(instance)

    def handle_set(self, instance, field_name, data, info, is_m2m, is_reverse):
        """Handle 'set' operation (replace all)."""
        model = type(instance)
        if is_m2m:
            field = model._meta.get_field(field_name)
            manager = getattr(instance, field_name)
            ids = data if isinstance(data, list) else [data]
            objs = []
            for item in ids:
                 pk = self._coerce_pk(item)
                 obj = self._get_tenant_queryset(field.related_model, info, operation="retrieve").get(pk=pk)
                 objs.append(obj)
            manager.set(objs)
        elif is_reverse:
             # For reverse, "set" implies:
             # 1. Disconnect all existing
             # 2. Connect new ones
             # OR if relation is non-nullable, delete existing? (Prisma deletes)
             # Here we try to nullify first.
             rel = self._get_reverse_relations(model).get(field_name)
             if not rel: return
             related_model = rel.related_model
             remote_field_name = rel.field.name

             # clear existing
             getattr(instance, field_name).all().update(**{remote_field_name: None})

             ids = data if isinstance(data, list) else [data]
             for item in ids:
                 pk = self._coerce_pk(item)
                 obj = self._get_tenant_queryset(related_model, info, operation="update").get(pk=pk)
                 setattr(obj, remote_field_name, instance)
                 self._save_instance(obj)
        else:
             # Singular FK/O2O: 'set' is same as 'connect' for singular
             self.handle_connect(instance, field_name, data, info, is_m2m=False, is_reverse=False)

    def handle_create(self, instance, field_name, data, info, is_m2m, is_reverse):
        """Handle 'create' operation."""
        model = type(instance)
        if is_m2m:
            field = model._meta.get_field(field_name)
            manager = getattr(instance, field_name)
            items = data if isinstance(data, list) else [data]
            for item_data in items:
                # self.handle_nested_create is available via Mixin
                obj = self.handle_nested_create(field.related_model, item_data, info=info)
                manager.add(obj)
        elif is_reverse:
             rel = self._get_reverse_relations(model).get(field_name)
             if not rel: return
             related_model = rel.related_model
             remote_field_name = rel.field.name
             items = data if isinstance(data, list) else [data]
             for item_data in items:
                 # Set the back-link using Unified Input format
                 item_data[remote_field_name] = {"connect": str(instance.pk)}
                 self.handle_nested_create(related_model, item_data, info=info)
        else:
             # Singular FK/O2O: create a new object and set it
             field = model._meta.get_field(field_name)
             obj = self.handle_nested_create(field.related_model, data, info=info)
             setattr(instance, field_name, obj)
             self._save_instance(instance)

    def handle_update(self, instance, field_name, data, info, is_m2m, is_reverse):
        """Handle 'update' operation."""
        model = type(instance)
        # Update usually implies: find object (by ID in data?) and update it.
        # Unified input for update is usually: { where: {id: ...}, data: {...} } or just {id: ..., ...}
        if is_m2m:
             field = model._meta.get_field(field_name)
             items = data if isinstance(data, list) else [data]
             for item_data in items:
                 if "id" in item_data:
                     pk = self._coerce_pk(item_data["id"])
                     obj = self._get_tenant_queryset(field.related_model, info, operation="retrieve").get(pk=pk)
                     self.handle_nested_update(field.related_model, item_data, obj, info=info)
        elif is_reverse:
             rel = self._get_reverse_relations(model).get(field_name)
             if not rel: return
             related_model = rel.related_model
             items = data if isinstance(data, list) else [data]
             for item_data in items:
                 if "id" in item_data:
                     pk = self._coerce_pk(item_data["id"])
                     obj = self._get_tenant_queryset(related_model, info, operation="retrieve").get(pk=pk)
                     self.handle_nested_update(related_model, item_data, obj, info=info)
        else:
             # Singular FK/O2O: update the linked object (or specified by id)
             field = model._meta.get_field(field_name)
             if "id" in data:
                 pk = self._coerce_pk(data["id"])
                 obj = self._get_tenant_queryset(field.related_model, info, operation="retrieve").get(pk=pk)
                 updated = self.handle_nested_update(field.related_model, data, obj, info=info)
                 setattr(instance, field_name, updated)
                 self._save_instance(instance)
             else:
                 # Update currently linked object
                 current = getattr(instance, field_name)
                 if current:
                     self.handle_nested_update(field.related_model, data, current, info=info)


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
