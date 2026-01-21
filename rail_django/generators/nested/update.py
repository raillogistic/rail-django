"""
Nested Update Operations Mixin

This module provides the mixin class for handling nested update operations
with validation and relationship management.
"""

import uuid
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models

import graphene


class NestedUpdateMixin:
    """
    Mixin class providing nested update operation functionality.

    This mixin handles:
    - Updating model instances with nested relationships
    - Foreign key relationship updates
    - Reverse relationship handling with orphan cleanup
    - Many-to-many relationship management
    """

    def handle_nested_update(
        self,
        model: type[models.Model],
        input_data: dict[str, Any],
        instance: models.Model,
        info: Optional[graphene.ResolveInfo] = None,
    ) -> models.Model:
        """
        Handles nested update operations with validation and relationship management.

        Args:
            model: Django model class
            input_data: Input data containing updates and nested relationships
            instance: Existing model instance to update
            info: GraphQL resolve info for context

        Returns:
            Updated model instance
        """
        try:
            self._ensure_operation_access(model, "update", info, instance=instance)
            self._enforce_tenant_access(instance, info, model, operation="update")

            processed_input = self._process_nested_fields(input_data)
            processed_input = self._apply_tenant_input(
                processed_input, info, model, operation="update"
            )

            regular_fields, nested_fields, m2m_fields, reverse_fields = (
                self._categorize_update_fields(model, processed_input)
            )

            # Update regular fields
            for field_name, value in regular_fields.items():
                setattr(instance, field_name, value)

            # Handle foreign key relationships
            self._handle_update_foreign_keys(model, instance, nested_fields, info)
            self._save_instance(instance)

            # Handle reverse and M2M relationships
            self._handle_update_reverse_relations(model, instance, reverse_fields, info)
            self._handle_update_m2m(model, instance, m2m_fields, info)

            return instance

        except ValidationError:
            raise
        except IntegrityError as e:
            self._handle_integrity_error(model, e, operation="update")
        except Exception as e:
            raise ValidationError(f"Failed to update {model.__name__}: {str(e)}")

    def _categorize_update_fields(
        self, model: type[models.Model], processed_input: dict[str, Any]
    ) -> tuple[dict, dict, dict, dict]:
        """Categorize input fields into regular, nested, m2m, and reverse fields."""
        regular_fields, nested_fields, m2m_fields, reverse_fields = {}, {}, {}, {}
        reverse_relations = self._get_reverse_relations(model)

        for field_name, value in processed_input.items():
            if field_name == "id":
                continue
            if field_name in reverse_relations:
                reverse_fields[field_name] = (reverse_relations[field_name], value)
                continue
            if not hasattr(model, field_name):
                continue

            try:
                field = model._meta.get_field(field_name)
            except Exception:
                regular_fields[field_name] = value
                continue

            if isinstance(field, (models.ForeignKey, models.OneToOneField)):
                nested_fields[field_name] = (field, value)
            elif isinstance(field, models.ManyToManyField):
                m2m_fields[field_name] = (field, value)
            else:
                regular_fields[field_name] = value

        return regular_fields, nested_fields, m2m_fields, reverse_fields

    def _handle_update_foreign_keys(
        self, model: type[models.Model], instance: models.Model,
        nested_fields: dict[str, tuple], info: Optional[graphene.ResolveInfo],
    ) -> None:
        """Handle foreign key relationships during update."""
        for field_name, (field, value) in nested_fields.items():
            if value is None:
                setattr(instance, field_name, None)
            elif isinstance(value, dict):
                if not self._should_use_nested_operations(model, field_name):
                    raise ValidationError(
                        f"Nested operations disabled for {model.__name__}.{field_name}."
                    )
                if "id" in value:
                    related_qs = self._get_tenant_queryset(
                        field.related_model, info, operation="retrieve"
                    )
                    related = related_qs.get(pk=value["id"])
                    updated = self.handle_nested_update(
                        field.related_model, value, related, info=info
                    )
                    setattr(instance, field_name, updated)
                else:
                    new_inst = self.handle_nested_create(
                        field.related_model, value, info=info
                    )
                    setattr(instance, field_name, new_inst)
            elif isinstance(value, (str, int, uuid.UUID)):
                pk_val = self._coerce_pk(value)
                try:
                    related_qs = self._get_tenant_queryset(
                        field.related_model, info, operation="retrieve"
                    )
                    related = related_qs.get(pk=pk_val)
                    self._ensure_operation_access(
                        field.related_model, "retrieve", info, instance=related
                    )
                    setattr(instance, field_name, related)
                except field.related_model.DoesNotExist:
                    raise ValidationError({
                        field_name: f"{field.related_model.__name__} with id '{value}' does not exist."
                    })

    def _handle_update_reverse_relations(
        self, model: type[models.Model], instance: models.Model,
        reverse_fields: dict[str, tuple], info: Optional[graphene.ResolveInfo],
    ) -> None:
        """Handle reverse relationships during update."""
        for field_name, (related_field, value) in reverse_fields.items():
            if value is None:
                continue
            if not self._should_use_nested_operations(model, field_name):
                if self._has_nested_payload(value):
                    raise ValidationError(
                        f"Nested operations disabled for {model.__name__}.{field_name}."
                    )
            if isinstance(value, list):
                self._update_reverse_list(
                    model, instance, related_field, value, field_name, info
                )

    def _update_reverse_list(
        self, model: type[models.Model], instance: models.Model,
        related_field, value: list, field_name: str,
        info: Optional[graphene.ResolveInfo],
    ) -> None:
        """Update reverse relationships from a list of items."""
        related_qs = self._get_tenant_queryset(
            related_field.related_model, info, operation="retrieve"
        )
        existing = list(related_qs.filter(**{related_field.field.name: instance.pk}))
        updated_ids = set()

        for item in value:
            if isinstance(item, dict):
                if "id" in item:
                    self._update_existing_reverse_item(
                        instance, related_field, item, updated_ids, info
                    )
                else:
                    new_obj = self._create_reverse_item(
                        instance, related_field, item, info
                    )
                    if hasattr(new_obj, "pk"):
                        updated_ids.add(new_obj.pk)
            elif isinstance(item, (str, int, uuid.UUID)):
                pk_val = self._coerce_pk(item)
                self._connect_reverse_item(instance, related_field, pk_val, info)
                updated_ids.add(pk_val)

        # Delete orphaned items
        for obj in existing:
            if obj.pk not in updated_ids:
                obj.delete()

    def _update_existing_reverse_item(
        self, instance: models.Model, related_field, item: dict,
        updated_ids: set, info: Optional[graphene.ResolveInfo],
    ) -> None:
        """Update an existing reverse relationship item."""
        try:
            related_qs = self._get_tenant_queryset(
                related_field.related_model, info, operation="retrieve"
            )
            obj = related_qs.get(pk=item["id"])
            self._ensure_operation_access(
                related_field.related_model, "update", info, instance=obj
            )
            # Ensure FK points to our instance
            if getattr(obj, related_field.field.name + "_id", None) != instance.pk:
                setattr(obj, related_field.field.name, instance)

            for key, val in item.items():
                if key != "id":
                    self._set_field_value(obj, key, val, info)
            self._save_instance(obj)
            updated_ids.add(int(item["id"]))
        except related_field.related_model.DoesNotExist:
            raise ValidationError(
                f"{related_field.related_model.__name__} with id {item['id']} not found"
            )

    def _set_field_value(
        self, obj: models.Model, key: str, val: Any,
        info: Optional[graphene.ResolveInfo],
    ) -> None:
        """Set a field value, handling FK fields specially."""
        try:
            field = obj._meta.get_field(key)
            if isinstance(field, models.ForeignKey):
                if val is None:
                    setattr(obj, key, None)
                elif isinstance(val, (str, int, uuid.UUID)):
                    pk = self._coerce_pk(val)
                    related_qs = self._get_tenant_queryset(
                        field.related_model, info, operation="retrieve"
                    )
                    setattr(obj, key, related_qs.get(pk=pk))
                elif isinstance(val, dict):
                    if "id" in val:
                        related_qs = self._get_tenant_queryset(
                            field.related_model, info, operation="retrieve"
                        )
                        rel = related_qs.get(pk=val["id"])
                        setattr(obj, key, self.handle_nested_update(
                            field.related_model, val, rel, info=info
                        ))
                    else:
                        setattr(obj, key, self.handle_nested_create(
                            field.related_model, val, info=info
                        ))
                else:
                    setattr(obj, key, val)
            else:
                setattr(obj, key, val)
        except Exception:
            setattr(obj, key, val)

    def _create_reverse_item(
        self, instance: models.Model, related_field, item: dict,
        info: Optional[graphene.ResolveInfo],
    ) -> models.Model:
        """Create a new reverse relationship item."""
        item[related_field.field.name] = instance.pk
        processed = {}
        for key, val in item.items():
            try:
                field = related_field.related_model._meta.get_field(key)
                if isinstance(field, models.ForeignKey):
                    processed[key] = self._resolve_fk_value(field, val, info)
                else:
                    processed[key] = val
            except Exception:
                processed[key] = val
        return self.handle_nested_create(related_field.related_model, processed, info=info)

    def _resolve_fk_value(
        self, field: models.ForeignKey, val: Any,
        info: Optional[graphene.ResolveInfo],
    ) -> Any:
        """Resolve a FK value to a model instance or None."""
        if val is None:
            return None
        if isinstance(val, (str, int, uuid.UUID)):
            pk = self._coerce_pk(val)
            return self._get_tenant_queryset(
                field.related_model, info, operation="retrieve"
            ).get(pk=pk)
        if isinstance(val, dict):
            if "id" in val:
                rel = self._get_tenant_queryset(
                    field.related_model, info, operation="retrieve"
                ).get(pk=val["id"])
                return self.handle_nested_update(field.related_model, val, rel, info=info)
            return self.handle_nested_create(field.related_model, val, info=info)
        if hasattr(val, "pk"):
            return val
        return val

    def _connect_reverse_item(
        self, instance: models.Model, related_field, pk_val: Any,
        info: Optional[graphene.ResolveInfo],
    ) -> None:
        """Connect an existing reverse item to the instance."""
        try:
            related_qs = self._get_tenant_queryset(
                related_field.related_model, info, operation="update"
            )
            obj = related_qs.get(pk=pk_val)
            self._ensure_operation_access(
                related_field.related_model, "update", info, instance=obj
            )
            setattr(obj, related_field.field.name, instance)
            self._save_instance(obj)
        except Exception as e:
            raise ValidationError(
                f"Failed to connect {related_field.related_model.__name__} "
                f"with id {pk_val}: {str(e)}"
            )

    def _handle_update_m2m(
        self, model: type[models.Model], instance: models.Model,
        m2m_fields: dict[str, tuple], info: Optional[graphene.ResolveInfo],
    ) -> None:
        """Handle many-to-many relationships during update."""
        for field_name, (field, value) in m2m_fields.items():
            if value is None:
                continue
            m2m_mgr = getattr(instance, field_name)
            use_nested = self._should_use_nested_operations(model, field_name)

            if isinstance(value, dict):
                if not use_nested and self._has_nested_payload(value):
                    raise ValidationError(
                        f"Nested operations disabled for {model.__name__}.{field_name}."
                    )
                self._apply_m2m_operations(field, value, m2m_mgr, info)
            elif isinstance(value, list):
                if not use_nested and self._has_nested_payload(value):
                    raise ValidationError(
                        f"Nested operations disabled for {model.__name__}.{field_name}."
                    )
                m2m_mgr.set(self._resolve_m2m_list(field, value, info))

    def _apply_m2m_operations(
        self, field: models.ManyToManyField, value: dict, m2m_mgr,
        info: Optional[graphene.ResolveInfo],
    ) -> None:
        """Apply M2M operations (set, connect, create, disconnect, update)."""
        if "set" in value and isinstance(value["set"], list):
            m2m_mgr.set(self._resolve_m2m_list(field, value["set"], info))

        if "connect" in value and isinstance(value["connect"], list):
            for item in value["connect"]:
                if isinstance(item, (str, int, uuid.UUID)):
                    pk = self._coerce_pk(item)
                    obj = self._get_tenant_queryset(
                        field.related_model, info, operation="retrieve"
                    ).get(pk=pk)
                    m2m_mgr.add(obj)

        if "create" in value and isinstance(value["create"], list):
            new_objs = [
                self.handle_nested_create(field.related_model, it, info=info)
                for it in value["create"]
            ]
            m2m_mgr.add(*new_objs)

        if "disconnect" in value and isinstance(value["disconnect"], list):
            for item in value["disconnect"]:
                if isinstance(item, (str, int, uuid.UUID)):
                    pk = self._coerce_pk(item)
                    obj = self._get_tenant_queryset(
                        field.related_model, info, operation="retrieve"
                    ).get(pk=pk)
                    m2m_mgr.remove(obj)

        if "update" in value and isinstance(value["update"], list):
            for item in value["update"]:
                if "id" in item:
                    rel = self._get_tenant_queryset(
                        field.related_model, info, operation="retrieve"
                    ).get(pk=item["id"])
                    self.handle_nested_update(field.related_model, item, rel, info=info)

    def _resolve_m2m_list(
        self, field: models.ManyToManyField, value: list,
        info: Optional[graphene.ResolveInfo],
    ) -> list:
        """Resolve a list of M2M items to model instances."""
        result = []
        for item in value:
            if isinstance(item, dict):
                obj = self._resolve_m2m_dict(field, item, info)
                if obj:
                    result.append(obj)
            elif isinstance(item, str):
                name_fld = getattr(field.related_model, "_nested_name_field", "name")
                result.append(
                    self.handle_nested_create(field.related_model, {name_fld: item}, info=info)
                )
            elif isinstance(item, (int, uuid.UUID)):
                result.append(
                    self._get_tenant_queryset(
                        field.related_model, info, operation="retrieve"
                    ).get(pk=item)
                )
        return result

    def _resolve_m2m_dict(
        self, field: models.ManyToManyField, item: dict,
        info: Optional[graphene.ResolveInfo],
    ) -> Optional[models.Model]:
        """Resolve a dict item to an M2M related model instance."""
        if "id" in item:
            try:
                obj = self._get_tenant_queryset(
                    field.related_model, info, operation="retrieve"
                ).get(pk=item["id"])
            except (ValueError, field.related_model.DoesNotExist):
                try:
                    from graphql_relay import from_global_id
                    _, decoded_id = from_global_id(item["id"])
                    obj = self._get_tenant_queryset(
                        field.related_model, info, operation="retrieve"
                    ).get(pk=decoded_id)
                except Exception:
                    obj = self._get_tenant_queryset(
                        field.related_model, info, operation="retrieve"
                    ).get(pk=item["id"])

            self._ensure_operation_access(
                field.related_model, "retrieve", info, instance=obj
            )
            update_data = {k: v for k, v in item.items() if k != "id"}
            if update_data:
                obj = self.handle_nested_update(
                    field.related_model, item, obj, info=info
                )
            return obj
        return self.handle_nested_create(field.related_model, item, info=info)
