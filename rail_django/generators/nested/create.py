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
            # First, process nested_ prefixed fields and extract them
            processed_input = self._process_nested_fields(input_data)
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

            # Handle reverse relationships after instance creation
            self._handle_create_reverse_relations(
                model, instance, reverse_fields, info
            )

            # Handle many-to-many relationships after instance creation
            self._handle_create_m2m(
                model, instance, m2m_fields, info
            )

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
        """Handle foreign key relationships during create."""
        for field_name, (field, value) in nested_fields.items():
            if value is None:
                continue

            use_nested = self._should_use_nested_operations(model, field_name)
            if isinstance(value, dict):
                if not use_nested:
                    raise ValidationError(
                        f"Nested operations are disabled for {model.__name__}.{field_name}. "
                        f"Use ID references instead."
                    )
                # Nested create
                if "id" in value:
                    # Update existing object
                    related_queryset = self._get_tenant_queryset(
                        field.related_model, info, operation="retrieve"
                    )
                    related_instance = related_queryset.get(pk=value["id"])
                    regular_fields[field_name] = self.handle_nested_update(
                        field.related_model, value, related_instance, info=info
                    )
                else:
                    # Create new object
                    regular_fields[field_name] = self.handle_nested_create(
                        field.related_model, value, info=info
                    )
            elif isinstance(value, (str, int, uuid.UUID)):
                # Reference to existing object - convert ID to model instance
                pk_value = value
                # Try to coerce to int if it looks like a digit string
                if isinstance(value, str) and value.isdigit():
                    try:
                        pk_value = int(value)
                    except (TypeError, ValueError):
                        pass

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
                    # Explicitly map error to the input field name
                    raise ValidationError(
                        {
                            field_name: f"{field.related_model.__name__} with id '{value}' does not exist."
                        }
                    )
                except (TypeError, ValueError):
                    # Ensure numeric coercion issues are mapped to the correct field
                    raise ValidationError(
                        {
                            field_name: f"Field '{field_name}' invalid ID format: '{value}'."
                        }
                    )
            elif hasattr(value, "pk"):
                # Already a model instance, use directly
                regular_fields[field_name] = value
            else:
                # For other types, try direct assignment
                regular_fields[field_name] = value

    def _handle_create_reverse_relations(
        self,
        model: type[models.Model],
        instance: models.Model,
        reverse_fields: dict[str, tuple],
        info: Optional[graphene.ResolveInfo],
    ) -> None:
        """Handle reverse relationships after instance creation."""
        for field_name, (related_field, value) in reverse_fields.items():
            if value is None:
                continue
            use_nested = self._should_use_nested_operations(model, field_name)

            # Handle different types of reverse relationship data
            if isinstance(value, list):
                if not use_nested and self._has_nested_payload(value):
                    raise ValidationError(
                        f"Nested operations are disabled for {model.__name__}.{field_name}. "
                        f"Use ID references instead."
                    )
                # List can contain either IDs or dicts
                for item in value:
                    if isinstance(item, dict):
                        # Create new object and set the foreign key to point to our instance
                        item[related_field.field.name] = instance.pk
                        self.handle_nested_create(
                            related_field.related_model, item, info=info
                        )
                    elif isinstance(item, (str, int, uuid.UUID)):
                        # Connect existing object to this instance
                        self._connect_existing_to_instance(
                            related_field, item, instance, field_name, info
                        )

            elif isinstance(value, dict):
                if not use_nested and self._has_nested_payload(value):
                    raise ValidationError(
                        f"Nested operations are disabled for {model.__name__}.{field_name}. "
                        f"Use ID references instead."
                    )
                # Handle operations like create, connect, disconnect
                if "create" in value:
                    create_data = value["create"]
                    if isinstance(create_data, list):
                        for item in create_data:
                            if isinstance(item, dict):
                                # Set the foreign key to point to our instance
                                item[related_field.field.name] = instance.pk
                                self.handle_nested_create(
                                    related_field.related_model, item, info=info
                                )
                    elif isinstance(create_data, dict):
                        # Single object to create
                        create_data[related_field.field.name] = instance.pk
                        self.handle_nested_create(
                            related_field.related_model, create_data, info=info
                        )

                if "connect" in value:
                    # Connect existing objects to this instance
                    connect_ids = value["connect"]
                    if isinstance(connect_ids, list):
                        related_queryset = self._get_tenant_queryset(
                            related_field.related_model,
                            info,
                            operation="update",
                        )
                        related_objects = related_queryset.filter(
                            pk__in=connect_ids
                        )
                        for related_obj in related_objects:
                            self._ensure_operation_access(
                                related_field.related_model,
                                "update",
                                info,
                                instance=related_obj,
                            )
                            setattr(
                                related_obj,
                                related_field.field.name,
                                instance,
                            )
                            self._save_instance(related_obj)

    def _connect_existing_to_instance(
        self,
        related_field,
        item_id,
        instance: models.Model,
        field_name: str,
        info: Optional[graphene.ResolveInfo],
    ) -> None:
        """Connect an existing object to the instance."""
        pk_value = item_id
        if isinstance(item_id, str) and item_id.isdigit():
            try:
                pk_value = int(item_id)
            except (TypeError, ValueError):
                pass

        try:
            related_queryset = self._get_tenant_queryset(
                related_field.related_model,
                info,
                operation="update",
            )
            related_obj = related_queryset.get(pk=pk_value)
            self._ensure_operation_access(
                related_field.related_model,
                "update",
                info,
                instance=related_obj,
            )
            setattr(
                related_obj, related_field.field.name, instance
            )
            self._save_instance(related_obj)
        except Exception as e:
            raise ValidationError(
                {
                    field_name: f"Failed to connect {related_field.related_model.__name__} with id {item_id}: {str(e)}"
                }
            )

    def _handle_create_m2m(
        self,
        model: type[models.Model],
        instance: models.Model,
        m2m_fields: dict[str, tuple],
        info: Optional[graphene.ResolveInfo],
    ) -> None:
        """Handle many-to-many relationships after instance creation."""
        for field_name, (field, value) in m2m_fields.items():
            if value is None:
                continue

            m2m_manager = getattr(instance, field_name)

            # Check if nested operations should be used for this field
            use_nested = self._should_use_nested_operations(model, field_name)

            if isinstance(value, list):
                related_objects = []
                for item in value:
                    if isinstance(item, dict) and use_nested:
                        if "id" in item:
                            # Reference existing object
                            related_queryset = self._get_tenant_queryset(
                                field.related_model, info, operation="retrieve"
                            )
                            related_obj = related_queryset.get(pk=item["id"])
                            self._ensure_operation_access(
                                field.related_model,
                                "retrieve",
                                info,
                                instance=related_obj,
                            )
                        else:
                            # Create new object only if nested operations are enabled
                            related_obj = self.handle_nested_create(
                                field.related_model, item, info=info
                            )
                        related_objects.append(related_obj)
                    elif isinstance(item, (str, int, uuid.UUID)):
                        # Direct ID reference - always allowed
                        related_queryset = self._get_tenant_queryset(
                            field.related_model, info, operation="retrieve"
                        )
                        related_obj = related_queryset.get(pk=item)
                        self._ensure_operation_access(
                            field.related_model,
                            "retrieve",
                            info,
                            instance=related_obj,
                        )
                        related_objects.append(related_obj)
                    elif isinstance(item, dict) and not use_nested:
                        # If nested is disabled but dict is provided, raise error
                        raise ValidationError(
                            f"Nested operations are disabled for {model.__name__}.{field_name}. "
                            f"Use ID references instead."
                        )

                m2m_manager.set(related_objects)

            elif isinstance(value, dict):
                if not use_nested:
                    if self._has_nested_payload(value):
                        raise ValidationError(
                            f"Nested operations are disabled for {model.__name__}.{field_name}. "
                            f"Use ID references instead."
                        )

                # Handle operations like connect, create, disconnect
                if "connect" in value:
                    connect_ids = value["connect"]
                    if isinstance(connect_ids, list):
                        related_queryset = self._get_tenant_queryset(
                            field.related_model, info, operation="retrieve"
                        )
                        existing_objects = related_queryset.filter(
                            pk__in=connect_ids
                        )
                        for related_obj in existing_objects:
                            self._ensure_operation_access(
                                field.related_model,
                                "retrieve",
                                info,
                                instance=related_obj,
                            )
                        m2m_manager.add(*existing_objects)

                if "create" in value:
                    create_data = value["create"]
                    if isinstance(create_data, list):
                        new_objects = [
                            self.handle_nested_create(
                                field.related_model, item, info=info
                            )
                            for item in create_data
                        ]
                        m2m_manager.add(*new_objects)

                if "disconnect" in value:
                    disconnect_ids = value["disconnect"]
                    if isinstance(disconnect_ids, list):
                        related_queryset = self._get_tenant_queryset(
                            field.related_model, info, operation="retrieve"
                        )
                        objects_to_remove = related_queryset.filter(
                            pk__in=disconnect_ids
                        )
                        for related_obj in objects_to_remove:
                            self._ensure_operation_access(
                                field.related_model,
                                "retrieve",
                                info,
                                instance=related_obj,
                            )
                        m2m_manager.remove(*objects_to_remove)
