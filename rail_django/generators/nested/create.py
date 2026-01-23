"""
Nested Create Operations Mixin

This module provides the mixin class for handling nested create operations
with validation and relationship management.
"""

import uuid
from typing import Any, Optional, Type

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models

import graphene
from .operations import RelationOperationProcessor

class NestedCreateMixin:
    """
    Mixin class providing nested create operation functionality.

    This mixin handles:
    - Creating model instances with nested relationships
    - Foreign key relationship creation and linking
    - Reverse relationship handling
    - Many-to-many relationship setup
    """

    def handle_nested_create(
        self,
        model: type[models.Model],
        input_data: dict[str, Any],
        parent_instance: Optional[models.Model] = None,
        info: Optional[graphene.ResolveInfo] = None,
    ) -> models.Model:
        """
        Handles nested create operations with validation and relationship management.

        Args:
            model: Django model class to create
            input_data: Input data containing nested relationships
            parent_instance: Parent model instance if this is a nested create
            info: GraphQL resolve info for context

        Returns:
            Created model instance

        Raises:
            ValidationError: If validation fails or circular references detected
        """
        try:
            self._ensure_operation_access(model, "create", info)
            # First, process nested_ prefixed fields (now Unified Input pass-through)
            processed_input = self.process_relation_input(input_data)
            processed_input = self._apply_tenant_input(
                processed_input, info, model, operation="create"
            )

            # Separate regular fields from nested relationship fields
            regular_fields = {}
            nested_fields = {}
            m2m_fields = {}
            reverse_fields = {}

            # Get reverse relationships for this model
            reverse_relations = self._get_reverse_relations(model)

            for field_name, value in processed_input.items():
                if field_name == "id":
                    continue  # Skip ID field

                # Check if this is a reverse relationship field
                if field_name in reverse_relations:
                    reverse_fields[field_name] = (reverse_relations[field_name], value)
                    continue

                if not hasattr(model, field_name):
                    continue

                try:
                    field = model._meta.get_field(field_name)
                except Exception:
                    # Handle properties and methods
                    regular_fields[field_name] = value
                    continue

                if isinstance(field, models.ForeignKey):
                    nested_fields[field_name] = (field, value)
                elif isinstance(field, models.OneToOneField):
                    nested_fields[field_name] = (field, value)
                elif isinstance(field, models.ManyToManyField):
                    m2m_fields[field_name] = (field, value)
                else:
                    regular_fields[field_name] = value

            # Handle foreign key relationships first
            self._handle_create_foreign_keys(
                model, nested_fields, regular_fields, info
            )

            # Create the main instance
            instance = model(**regular_fields)
            self._save_instance(instance)

            # Handle relations using Processor
            processor = RelationOperationProcessor(self)

            # Handle reverse relationships
            for field_name, (rel, value) in reverse_fields.items():
                if value:
                     processor.process_relation(instance, field_name, value, info, is_reverse=True)

            # Handle many-to-many relationships
            for field_name, (field, value) in m2m_fields.items():
                if value:
                     processor.process_relation(instance, field_name, value, info, is_m2m=True)

            return instance

        except ValidationError as e:
            # Preserve field-specific errors so mutation can map them to fields
            raise e
        except IntegrityError as e:
            self._handle_integrity_error(model, e, operation="create")
        except Exception as e:
            # Wrap non-validation exceptions with context
            raise ValidationError(f"Failed to create {model.__name__}: {str(e)}")

    def _handle_create_foreign_keys(
        self,
        model: type[models.Model],
        nested_fields: dict[str, tuple],
        regular_fields: dict[str, Any],
        info: Optional[graphene.ResolveInfo],
    ) -> None:
        """Handle foreign key relationships during create (Unified Input)."""
        for field_name, (field, value) in nested_fields.items():
            if value is None:
                continue
                
            if not isinstance(value, dict):
                 continue
                 
            if "connect" in value:
                pk_value = self._coerce_pk(value["connect"])
                try:
                    related_queryset = self._get_tenant_queryset(
                        field.related_model, info, operation="retrieve"
                    )
                    related_instance = related_queryset.get(pk=pk_value)
                    self._ensure_operation_access(
                        field.related_model,
                        "retrieve",
                        info,
                        instance=related_instance,
                    )
                    regular_fields[field_name] = related_instance
                except field.related_model.DoesNotExist:
                    raise ValidationError(
                        {
                            field_name: f"{field.related_model.__name__} with id '{pk_value}' does not exist."
                        }
                    )
            elif "create" in value:
                create_data = value["create"]
                related_instance = self.handle_nested_create(
                    field.related_model, create_data, info=info
                )
                regular_fields[field_name] = related_instance
            elif "update" in value:
                # Update existing and link
                update_payload = value["update"]
                if "id" not in update_payload:
                     continue # Cannot identify object to update
                pk_value = self._coerce_pk(update_payload["id"])
                try:
                    related_queryset = self._get_tenant_queryset(
                        field.related_model, info, operation="retrieve"
                    )
                    related_instance = related_queryset.get(pk=pk_value)
                    updated_instance = self.handle_nested_update(
                        field.related_model, update_payload, related_instance, info=info
                    )
                    regular_fields[field_name] = updated_instance
                except field.related_model.DoesNotExist:
                     raise ValidationError({field_name: f"Object not found for update."})