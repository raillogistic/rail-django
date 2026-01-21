"""
Nested Delete Operations Mixin

This module provides the mixin class for handling cascade delete operations
and validation utilities for nested operations.
"""

from typing import Any, Optional, Type

from django.core.exceptions import ValidationError
from django.db import models


class NestedDeleteMixin:
    """
    Mixin class providing nested delete and validation functionality.

    This mixin handles:
    - Cascade delete operations with configurable rules
    - Nested data validation
    - Circular reference detection
    - Field value validation
    """

    def handle_cascade_delete(
        self, instance: models.Model, cascade_rules: Optional[dict[str, str]] = None
    ) -> list[str]:
        """
        Handles cascade delete operations with configurable cascade rules.

        Args:
            instance: Model instance to delete
            cascade_rules: Dictionary mapping field names to cascade actions
                          ('CASCADE', 'PROTECT', 'SET_NULL', 'SET_DEFAULT')

        Returns:
            List of deleted object descriptions
        """
        deleted_objects = []

        try:
            # Get all related objects
            related_objects = []
            for field in instance._meta.get_fields():
                if hasattr(field, "related_model") and hasattr(
                    field, "get_accessor_name"
                ):
                    accessor_name = field.get_accessor_name()
                    if hasattr(instance, accessor_name):
                        related_manager = getattr(instance, accessor_name)
                        if hasattr(related_manager, "all"):
                            related_objects.extend(list(related_manager.all()))

            # Apply cascade rules
            for related_obj in related_objects:
                field_name = related_obj._meta.model_name
                cascade_action = (
                    cascade_rules.get(field_name, "CASCADE")
                    if cascade_rules
                    else "CASCADE"
                )

                if cascade_action == "CASCADE":
                    # Recursively delete related objects
                    nested_deleted = self.handle_cascade_delete(
                        related_obj, cascade_rules
                    )
                    deleted_objects.extend(nested_deleted)
                elif cascade_action == "PROTECT":
                    # Prevent deletion if related objects exist
                    raise ValidationError(
                        f"Cannot delete {instance._meta.model_name} because it has "
                        f"related {field_name} objects"
                    )
                elif cascade_action == "SET_NULL":
                    # Set foreign key to NULL (if nullable)
                    for fk_field in related_obj._meta.get_fields():
                        if (
                            isinstance(fk_field, models.ForeignKey)
                            and fk_field.related_model == instance._meta.model
                            and fk_field.null
                        ):
                            setattr(related_obj, fk_field.name, None)
                            related_obj.save()

            # Delete the main instance
            instance_description = f"{instance._meta.model_name}(id={instance.pk})"
            instance.delete()
            deleted_objects.append(instance_description)

            return deleted_objects

        except Exception as e:
            raise ValidationError(
                f"Failed to delete {instance._meta.model_name}: {str(e)}"
            )

    def validate_nested_data(
        self,
        model: type[models.Model],
        input_data: dict[str, Any],
        operation: str = "create",
    ) -> list[str]:
        """
        Validates nested input data before processing.

        Args:
            model: Django model class
            input_data: Input data to validate
            operation: Operation type ('create' or 'update')

        Returns:
            List of validation error messages
        """
        errors = []

        try:
            # Check for circular references
            if self._has_circular_reference(model, input_data):
                errors.append("Circular reference detected in nested data")

            # Validate required fields for create operations
            if operation == "create":
                required_fields = [
                    field.name
                    for field in model._meta.get_fields()
                    if (
                        hasattr(field, "null")
                        and not field.null
                        and not hasattr(field, "default")
                        and not getattr(field, "auto_now", False)
                        and not getattr(field, "auto_now_add", False)
                    )
                ]

                for required_field in required_fields:
                    if required_field not in input_data:
                        errors.append(f"Required field '{required_field}' is missing")

            # Validate field types and constraints
            for field_name, value in input_data.items():
                if not hasattr(model, field_name):
                    continue

                try:
                    field = model._meta.get_field(field_name)
                    field_errors = self._validate_field_value(field, value)
                    errors.extend(field_errors)
                except Exception:
                    continue  # Skip non-model fields

            return errors

        except Exception as e:
            return [f"Validation error: {str(e)}"]

    def _has_circular_reference(
        self,
        model: type[models.Model],
        input_data: dict[str, Any],
        visited_models: Optional[set[type[models.Model]]] = None,
    ) -> bool:
        """
        Checks for circular references in nested data.

        Args:
            model: Django model class being checked
            input_data: Input data to check for circular references
            visited_models: Set of models already visited in the chain

        Returns:
            bool: True if circular reference detected, False otherwise
        """
        if visited_models is None:
            visited_models = set()

        if model in visited_models:
            return True

        visited_models.add(model)

        for field_name, value in input_data.items():
            if isinstance(value, dict) and hasattr(model, field_name):
                try:
                    field = model._meta.get_field(field_name)
                    if hasattr(field, "related_model"):
                        if self._has_circular_reference(
                            field.related_model, value, visited_models.copy()
                        ):
                            return True
                except Exception:
                    continue

        return False

    def _validate_field_value(self, field: models.Field, value: Any) -> list[str]:
        """
        Validates a field value against field constraints.

        Args:
            field: Django model field
            value: Value to validate

        Returns:
            List of validation error messages
        """
        errors = []

        try:
            # Check null constraints
            if value is None and hasattr(field, "null") and not field.null:
                errors.append(f"Field '{field.name}' cannot be null")

            # Check string length constraints
            if (
                isinstance(field, (models.CharField, models.TextField))
                and value is not None
            ):
                if hasattr(field, "max_length") and field.max_length:
                    if len(str(value)) > field.max_length:
                        errors.append(
                            f"Field '{field.name}' exceeds maximum length of {field.max_length}"
                        )

            # Check numeric constraints
            if (
                isinstance(field, (models.IntegerField, models.FloatField))
                and value is not None
            ):
                try:
                    if isinstance(field, models.IntegerField):
                        int(value)
                    else:
                        float(value)
                except (ValueError, TypeError):
                    errors.append(f"Field '{field.name}' must be a valid number")

            # Check choice constraints
            if hasattr(field, "choices") and field.choices and value is not None:
                valid_choices = [choice[0] for choice in field.choices]
                if value not in valid_choices:
                    errors.append(
                        f"Field '{field.name}' must be one of: {valid_choices}"
                    )

            return errors

        except Exception as e:
            return [f"Field validation error for '{field.name}': {str(e)}"]
