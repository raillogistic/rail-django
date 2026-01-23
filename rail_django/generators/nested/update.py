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
from .operations import RelationOperationProcessor

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

            processed_input = self.process_relation_input(input_data)
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

            # Handle reverse and M2M relationships using Processor
            processor = RelationOperationProcessor(self)

            for field_name, (rel, value) in reverse_fields.items():
                if value:
                     processor.process_relation(instance, field_name, value, info, is_reverse=True)

            for field_name, (field, value) in m2m_fields.items():
                 if value:
                     processor.process_relation(instance, field_name, value, info, is_m2m=True)

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
        """Handle foreign key relationships during update (Unified Input)."""
        for field_name, (field, value) in nested_fields.items():
            if value is None:
                setattr(instance, field_name, None)
                continue
            
            if not isinstance(value, dict): continue

            if "connect" in value:
                pk_val = self._coerce_pk(value["connect"])
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
                        field_name: f"{field.related_model.__name__} with id '{pk_val}' does not exist."
                    })
            elif "create" in value:
                new_inst = self.handle_nested_create(
                    field.related_model, value["create"], info=info
                )
                setattr(instance, field_name, new_inst)
            elif "update" in value:
                 # Update existing linked object (if ID provided) OR update currently linked?
                 # Unified semantics usually imply 'update' has 'where' or 'data'.
                 # If we just provide 'update: {...}', does it update the CURRENTLY linked object?
                 # Prisma: update(data: ...). Updates the relation.
                 # If value["update"] has ID, we update that ID and link it (if not linked).
                 # If no ID, we might default to updating the currently linked object?
                 update_data = value["update"]
                 if "id" in update_data:
                      pk = self._coerce_pk(update_data["id"])
                      related = self._get_tenant_queryset(field.related_model, info).get(pk=pk)
                      updated = self.handle_nested_update(field.related_model, update_data, related, info=info)
                      setattr(instance, field_name, updated)
                 else:
                      # Try to update currently linked object
                      current = getattr(instance, field_name)
                      if current:
                           updated = self.handle_nested_update(field.related_model, update_data, current, info=info)
                           # no need to setattr if it's the same instance, but safe to do so
                      else:
                           pass # Nothing to update
            elif "disconnect" in value:
                 # Boolean true? or ID?
                 # If boolean true, disconnect current.
                 setattr(instance, field_name, None)