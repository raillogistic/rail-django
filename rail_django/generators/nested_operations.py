"""
Nested Operations System for Django GraphQL Auto-Generation

This module provides advanced nested create/update operations with comprehensive
validation, transaction management, and cascade handling for related objects.
"""

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Set, Type, Union

import graphene
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Q

from ..core.error_handling import get_error_handler
from ..core.performance import get_query_optimizer
from ..core.security import get_authz_manager, get_input_validator
from ..core.settings import MutationGeneratorSettings

logger = logging.getLogger(__name__)


class NestedOperationHandler:
    """
    Handles complex nested operations for GraphQL mutations including
    nested creates, updates, and cascade operations with proper validation.

    This class supports:
    - Hierarchical settings configuration
    - Security and authorization integration
    - Input validation and error handling
    - Performance optimization
    - Circular reference detection
    - Transaction management
    """

    def __init__(self, mutation_settings=None, schema_name: str = "default"):
        """
        Initialize the NestedOperationHandler.

        Args:
            mutation_settings: Mutation generator settings or None for defaults
            schema_name: Name of the schema for multi-schema support
        """
        self._processed_objects: Set[str] = set()
        self._validation_errors: List[str] = []
        self.schema_name = schema_name

        # Use hierarchical settings if no explicit settings provided
        if mutation_settings is None:
            self.mutation_settings = MutationGeneratorSettings.from_schema(schema_name)
        else:
            self.mutation_settings = mutation_settings

        # Initialize security and performance components
        self.authorization_manager = get_authz_manager(schema_name)
        self.input_validator = get_input_validator(schema_name)
        self.error_handler = get_error_handler(schema_name)
        self.query_optimizer = get_query_optimizer(schema_name)

        self.circular_reference_tracker = set()
        self.max_depth = getattr(
            self.mutation_settings, "max_nested_depth", 10
        )  # Prevent infinite recursion

    def _should_use_nested_operations(self, model, field_name):
        """
        Check if nested operations should be used for a specific field.

        Args:
            model: Django model class
            field_name: Name of the field to check

        Returns:
            bool: True if nested operations should be used, False for ID-only operations
        """
        if not self.mutation_settings:
            return True  # Default to nested operations if no settings

        model_name = model.__name__

        # Check per-field configuration first (highest priority)
        if hasattr(self.mutation_settings, "nested_field_config"):
            field_config = self.mutation_settings.nested_field_config
            if model_name in field_config and field_name in field_config[model_name]:
                return field_config[model_name][field_name]

        # Check per-model configuration
        if hasattr(self.mutation_settings, "nested_relations_config"):
            model_config = self.mutation_settings.nested_relations_config
            if model_name in model_config:
                return model_config[model_name]

        # Check global configuration
        if hasattr(self.mutation_settings, "enable_nested_relations"):
            return self.mutation_settings.enable_nested_relations

        # Default to enabled
        return True

    def handle_nested_create(
        self,
        model: Type[models.Model],
        input_data: Dict[str, Any],
        parent_instance: Optional[models.Model] = None,
    ) -> models.Model:
        """
        Handles nested create operations with validation and relationship management.

        Args:
            model: Django model class to create
            input_data: Input data containing nested relationships
            parent_instance: Parent model instance if this is a nested create

        Returns:
            Created model instance

        Raises:
            ValidationError: If validation fails or circular references detected
        """
        try:
            # First, process nested_ prefixed fields and extract them
            processed_input = self._process_nested_fields(input_data)

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
                except:
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
            for field_name, (field, value) in nested_fields.items():
                if value is None:
                    continue

                if isinstance(value, dict):
                    # Nested create
                    if "id" in value:
                        # Update existing object
                        related_instance = field.related_model.objects.get(
                            pk=value["id"]
                        )
                        regular_fields[field_name] = self.handle_nested_update(
                            field.related_model, value, related_instance
                        )
                    else:
                        # Create new object
                        regular_fields[field_name] = self.handle_nested_create(
                            field.related_model, value
                        )
                elif isinstance(value, (str, int, uuid.UUID)):
                    # Reference to existing object - convert ID to model instance
                    pk_value = value
                    # Try to coerce to int if it looks like a digit string, but keep as-is otherwise (for UUIDs/Slugs)
                    if isinstance(value, str) and value.isdigit():
                        try:
                            pk_value = int(value)
                        except (TypeError, ValueError):
                            pass

                    try:
                        related_instance = field.related_model.objects.get(pk=pk_value)
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

            # Create the main instance
            instance = model.objects.create(**regular_fields)

            # Handle reverse relationships after instance creation
            for field_name, (related_field, value) in reverse_fields.items():
                if value is None:
                    continue

                # Handle different types of reverse relationship data
                if isinstance(value, list):
                    # List can contain either IDs (to connect existing objects) or dicts (to create new objects)
                    for item in value:
                        if isinstance(item, dict):
                            # Create new object and set the foreign key to point to our instance
                            item[related_field.field.name] = instance.pk
                            self.handle_nested_create(related_field.related_model, item)
                        elif isinstance(item, (str, int, uuid.UUID)):
                            # Connect existing object to this instance
                            pk_value = item
                            if isinstance(item, str) and item.isdigit():
                                try:
                                    pk_value = int(item)
                                except (TypeError, ValueError):
                                    pass

                            try:
                                related_field.related_model.objects.filter(
                                    pk=pk_value
                                ).update(**{related_field.field.name: instance})
                            except Exception as e:
                                raise ValidationError(
                                    {
                                        field_name: f"Failed to connect {related_field.related_model.__name__} with id {item}: {str(e)}"
                                    }
                                )

                elif isinstance(value, dict):
                    # Handle operations like create, connect, disconnect
                    if "create" in value:
                        create_data = value["create"]
                        if isinstance(create_data, list):
                            for item in create_data:
                                if isinstance(item, dict):
                                    # Set the foreign key to point to our instance
                                    item[related_field.field.name] = instance.pk
                                    self.handle_nested_create(
                                        related_field.related_model, item
                                    )
                        elif isinstance(create_data, dict):
                            # Single object to create
                            create_data[related_field.field.name] = instance.pk
                            self.handle_nested_create(
                                related_field.related_model, create_data
                            )

                    if "connect" in value:
                        # Connect existing objects to this instance
                        connect_ids = value["connect"]
                        if isinstance(connect_ids, list):
                            related_field.related_model.objects.filter(
                                pk__in=connect_ids
                            ).update(**{related_field.field.name: instance})

            # Handle many-to-many relationships after instance creation
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
                                related_obj = field.related_model.objects.get(
                                    pk=item["id"]
                                )
                            else:
                                # Create new object only if nested operations are enabled
                                related_obj = self.handle_nested_create(
                                    field.related_model, item
                                )
                            related_objects.append(related_obj)
                        elif isinstance(item, (str, int, uuid.UUID)):
                            # Direct ID reference - always allowed
                            related_obj = field.related_model.objects.get(pk=item)
                            related_objects.append(related_obj)
                        elif isinstance(item, dict) and not use_nested:
                            # If nested is disabled but dict is provided, raise error
                            raise ValidationError(
                                f"Nested operations are disabled for {model.__name__}.{field_name}. "
                                f"Use ID references instead."
                            )

                    m2m_manager.set(related_objects)
                elif isinstance(value, dict):
                    # Check if nested operations should be used for this field
                    use_nested = self._should_use_nested_operations(model, field_name)

                    if not use_nested:
                        raise ValidationError(
                            f"Nested operations are disabled for {model.__name__}.{field_name}. "
                            f"Use ID references instead."
                        )

                    # Handle operations like connect, create, disconnect
                    if "connect" in value:
                        connect_ids = value["connect"]
                        if isinstance(connect_ids, list):
                            existing_objects = field.related_model.objects.filter(
                                pk__in=connect_ids
                            )
                            m2m_manager.add(*existing_objects)

                    if "create" in value:
                        create_data = value["create"]
                        if isinstance(create_data, list):
                            new_objects = [
                                self.handle_nested_create(field.related_model, item)
                                for item in create_data
                            ]
                            m2m_manager.add(*new_objects)

                    if "disconnect" in value:
                        disconnect_ids = value["disconnect"]
                        if isinstance(disconnect_ids, list):
                            objects_to_remove = field.related_model.objects.filter(
                                pk__in=disconnect_ids
                            )
                            m2m_manager.remove(*objects_to_remove)

            return instance

        except ValidationError as e:
            # Preserve field-specific errors so mutation can map them to fields
            raise e
        except IntegrityError as e:
            # Attempt to parse constraint violations and map to fields
            error_msg = str(e)

            # Handle not-null constraint violations (French message)
            match = re.search(r'null value in column "(\w+)".*violates not-null constraint', error_msg)
            if match:
                column_name = match.group(1)
                field_name = self._map_column_to_field(model, column_name) or column_name
                # Prefer verbose_name when available
                label = self._get_field_verbose_name(model, field_name) or field_name
                # French: "ne peut pas être nul"
                raise ValidationError({field_name: f"Le champ '{label}' ne peut pas être nul."})

            # Handle unique constraint violations (French message)
            fields = self._extract_unique_constraint_fields(model, e)
            if fields:
                # Provide a clear French message without leaking raw DB error details
                # Use verbose_name if available for user-facing clarity
                return_errors = {}
                for field in fields:
                    label = self._get_field_verbose_name(model, field) or field
                    return_errors[field] = (
                        f"Doublon détecté: la valeur du champ '{label}' existe déjà. Veuillez fournir une valeur unique."
                    )
                raise ValidationError(return_errors)

            # Fallback to generic message in French if fields cannot be determined
            raise ValidationError(f"Échec de la création de {model.__name__} : {str(e)}")

        except Exception as e:
            # Wrap non-validation exceptions with context
            raise ValidationError(f"Failed to create {model.__name__}: {str(e)}")

    def handle_nested_update(
        self,
        model: Type[models.Model],
        input_data: Dict[str, Any],
        instance: models.Model,
    ) -> models.Model:
        """
        Handles nested update operations with validation and relationship management.

        Args:
            model: Django model class
            input_data: Input data containing updates and nested relationships
            instance: Existing model instance to update

        Returns:
            Updated model instance
        """
        try:
            # First, process nested_ prefixed fields and extract them
            processed_input = self._process_nested_fields(input_data)

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
                except:
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

            # Update regular fields
            for field_name, value in regular_fields.items():
                setattr(instance, field_name, value)

            # Handle foreign key relationships
            for field_name, (field, value) in nested_fields.items():
                if value is None:
                    setattr(instance, field_name, None)
                elif isinstance(value, dict):
                    if "id" in value:
                        # Update existing related object
                        related_instance = field.related_model.objects.get(
                            pk=value["id"]
                        )
                        updated_instance = self.handle_nested_update(
                            field.related_model, value, related_instance
                        )
                        setattr(instance, field_name, updated_instance)
                    else:
                        # Create new related object
                        new_instance = self.handle_nested_create(
                            field.related_model, value
                        )
                        setattr(instance, field_name, new_instance)
                elif isinstance(value, (str, int, uuid.UUID)):
                    # Reference to existing object
                    pk_value = value
                    if isinstance(value, str) and value.isdigit():
                        try:
                            pk_value = int(value)
                        except (TypeError, ValueError):
                            pass

                    try:
                        related_instance = field.related_model.objects.get(pk=pk_value)
                        setattr(instance, field_name, related_instance)
                    except field.related_model.DoesNotExist:
                        raise ValidationError(
                            {
                                field_name: f"{field.related_model.__name__} with id '{value}' does not exist."
                            }
                        )
                    except (TypeError, ValueError):
                        raise ValidationError(
                            {
                                field_name: f"Field '{field_name}' invalid ID format: '{value}'."
                            }
                        )

            # Save the instance
            instance.save()

            # Handle reverse relationships (e.g., updating comments for a post)
            for field_name, (related_field, value) in reverse_fields.items():
                if value is None:
                    continue

                # Handle different types of reverse relationship data
                if isinstance(value, list):
                    # Get all existing related objects for this instance
                    existing_objects = list(
                        related_field.related_model.objects.filter(
                            **{related_field.field.name: instance.pk}
                        )
                    )

                    # Track which existing objects are being updated
                    updated_object_ids = set()

                    # Process each item in the nested field
                    for item in value:
                        if isinstance(item, dict):
                            if "id" in item:
                                # Update existing object
                                try:
                                    existing_obj = (
                                        related_field.related_model.objects.get(
                                            pk=item["id"]
                                        )
                                    )
                                    # Ensure the object belongs to this instance
                                    if (
                                        getattr(
                                            existing_obj,
                                            related_field.field.name + "_id",
                                        )
                                        != instance.pk
                                    ):
                                        # Set the foreign key to point to our instance
                                        setattr(
                                            existing_obj,
                                            related_field.field.name,
                                            instance,
                                        )

                                    # Update the existing object with new data
                                    for key, val in item.items():
                                        if key != "id":
                                            # Handle foreign key fields properly
                                            try:
                                                field = existing_obj._meta.get_field(
                                                    key
                                                )
                                                if isinstance(field, models.ForeignKey):
                                                    if val is None:
                                                        setattr(existing_obj, key, None)
                                                    elif isinstance(val, (str, int, uuid.UUID)):
                                                        # Convert ID to related object instance
                                                        pk_val = val
                                                        if isinstance(val, str) and val.isdigit():
                                                            try:
                                                                pk_val = int(val)
                                                            except (TypeError, ValueError):
                                                                pass
                                                        
                                                        related_obj = field.related_model.objects.get(
                                                            pk=pk_val
                                                        )
                                                        setattr(
                                                            existing_obj,
                                                            key,
                                                            related_obj,
                                                        )
                                                    elif isinstance(val, dict):
                                                        # Handle nested object creation/update
                                                        if "id" in val:
                                                            related_obj = field.related_model.objects.get(
                                                                pk=val["id"]
                                                            )
                                                            updated_related = self.handle_nested_update(
                                                                field.related_model,
                                                                val,
                                                                related_obj,
                                                            )
                                                            setattr(
                                                                existing_obj,
                                                                key,
                                                                updated_related,
                                                            )
                                                        else:
                                                            new_related = self.handle_nested_create(
                                                                field.related_model, val
                                                            )
                                                            setattr(
                                                                existing_obj,
                                                                key,
                                                                new_related,
                                                            )
                                                    else:
                                                        setattr(existing_obj, key, val)
                                                else:
                                                    setattr(existing_obj, key, val)
                                            except:
                                                # Fallback to direct assignment for non-model fields
                                                setattr(existing_obj, key, val)
                                    existing_obj.save()
                                    updated_object_ids.add(
                                        int(item["id"])
                                    )  # Convert to int for consistent comparison
                                except related_field.related_model.DoesNotExist:
                                    raise ValidationError(
                                        f"{related_field.related_model.__name__} with id {item['id']} does not exist"
                                    )
                            else:
                                # Create new object and set the foreign key to point to our instance
                                item[related_field.field.name] = instance.pk

                                # Handle foreign key fields in the new object data
                                processed_item = {}
                                for key, val in item.items():
                                    try:
                                        field = (
                                            related_field.related_model._meta.get_field(
                                                key
                                            )
                                        )
                                        if isinstance(field, models.ForeignKey):
                                            if val is None:
                                                processed_item[key] = None
                                            elif isinstance(val, (str, int, uuid.UUID)):
                                                # Convert ID to related object instance
                                                pk_val = val
                                                if isinstance(val, str) and val.isdigit():
                                                    try:
                                                        pk_val = int(val)
                                                    except (TypeError, ValueError):
                                                        pass

                                                related_obj = (
                                                    field.related_model.objects.get(
                                                        pk=pk_val
                                                    )
                                                )
                                                processed_item[key] = related_obj
                                            elif isinstance(val, dict):
                                                # Handle nested object creation/update
                                                if "id" in val:
                                                    related_obj = (
                                                        field.related_model.objects.get(
                                                            pk=val["id"]
                                                        )
                                                    )
                                                    updated_related = (
                                                        self.handle_nested_update(
                                                            field.related_model,
                                                            val,
                                                            related_obj,
                                                        )
                                                    )
                                                    processed_item[key] = (
                                                        updated_related
                                                    )
                                                else:
                                                    new_related = (
                                                        self.handle_nested_create(
                                                            field.related_model, val
                                                        )
                                                    )
                                                    processed_item[key] = new_related
                                            elif hasattr(val, "pk"):
                                                # Already a model instance, use directly
                                                processed_item[key] = val
                                            else:
                                                processed_item[key] = val
                                        else:
                                            processed_item[key] = val
                                    except:
                                        # Fallback to direct assignment for non-model fields
                                        processed_item[key] = val

                                new_obj = self.handle_nested_create(
                                    related_field.related_model, processed_item
                                )
                                if hasattr(new_obj, "pk"):
                                    updated_object_ids.add(new_obj.pk)
                        elif isinstance(item, (str, int, uuid.UUID)):
                            # Connect existing object to this instance
                            pk_val = item
                            if isinstance(item, str) and item.isdigit():
                                try:
                                    pk_val = int(item)
                                except (TypeError, ValueError):
                                    pass

                            try:
                                related_field.related_model.objects.filter(
                                    pk=pk_val
                                ).update(**{related_field.field.name: instance})
                                updated_object_ids.add(
                                    pk_val
                                )  # Store actual PK value
                            except Exception as e:
                                raise ValidationError(
                                    f"Failed to connect {related_field.related_model.__name__} with id {item}: {str(e)}"
                                )

                    # Delete old items that are not present in the new nested field data
                    objects_to_delete = [
                        obj
                        for obj in existing_objects
                        if obj.pk not in updated_object_ids
                    ]

                    for obj_to_delete in objects_to_delete:
                        obj_to_delete.delete()

            # Handle many-to-many relationships
            for field_name, (field, value) in m2m_fields.items():
                if value is None:
                    continue

                m2m_manager = getattr(instance, field_name)

                if isinstance(value, dict):
                    # Handle operations like connect, create, disconnect, set
                    if "set" in value:
                        # Replace all relationships
                        set_data = value["set"]
                        if isinstance(set_data, list):
                            related_objects = []
                            for item in set_data:
                                if isinstance(item, dict):
                                    if "id" in item:
                                        related_obj = field.related_model.objects.get(
                                            pk=item["id"]
                                        )
                                    else:
                                        related_obj = self.handle_nested_create(
                                            field.related_model, item
                                        )
                                    related_objects.append(related_obj)
                                elif isinstance(item, (str, int, uuid.UUID)):
                                    pk_val = item
                                    if isinstance(item, str) and item.isdigit():
                                        try:
                                            pk_val = int(item)
                                        except (TypeError, ValueError):
                                            pass
                                    related_obj = field.related_model.objects.get(
                                        pk=pk_val
                                    )
                                    related_objects.append(related_obj)
                            m2m_manager.set(related_objects)

                    if "connect" in value:
                        # Add relationships
                        connect_data = value["connect"]
                        if isinstance(connect_data, list):
                            for item in connect_data:
                                if isinstance(item, (str, int, uuid.UUID)):
                                    pk_val = item
                                    if isinstance(item, str) and item.isdigit():
                                        try:
                                            pk_val = int(item)
                                        except (TypeError, ValueError):
                                            pass
                                    related_obj = field.related_model.objects.get(
                                        pk=pk_val
                                    )
                                    m2m_manager.add(related_obj)

                    if "create" in value:
                        # Create and connect new objects
                        create_data = value["create"]
                        if isinstance(create_data, list):
                            new_objects = [
                                self.handle_nested_create(field.related_model, item)
                                for item in create_data
                            ]
                            m2m_manager.add(*new_objects)

                    if "disconnect" in value:
                        # Remove relationships
                        disconnect_data = value["disconnect"]
                        if isinstance(disconnect_data, list):
                            for item in disconnect_data:
                                if isinstance(item, (str, int, uuid.UUID)):
                                    pk_val = item
                                    if isinstance(item, str) and item.isdigit():
                                        try:
                                            pk_val = int(item)
                                        except (TypeError, ValueError):
                                            pass
                                    related_obj = field.related_model.objects.get(
                                        pk=pk_val
                                    )
                                    m2m_manager.remove(related_obj)

                    if "update" in value:
                        # Update existing related objects
                        update_data = value["update"]
                        if isinstance(update_data, list):
                            for item in update_data:
                                if "id" in item:
                                    related_instance = field.related_model.objects.get(
                                        pk=item["id"]
                                    )
                                    self.handle_nested_update(
                                        field.related_model, item, related_instance
                                    )

                elif isinstance(value, list):
                    # Handle simple list of strings/dicts for nested creation
                    related_objects = []
                    for item in value:
                        if isinstance(item, dict):
                            if "id" in item:
                                # Get existing object by ID - handle both regular and GraphQL IDs
                                try:
                                    # Try to use the ID as-is first (for integer IDs)
                                    related_obj = field.related_model.objects.get(
                                        pk=item["id"]
                                    )
                                except (ValueError, field.related_model.DoesNotExist):
                                    # If that fails, try to decode as GraphQL global ID
                                    from graphql_relay import from_global_id

                                    try:
                                        decoded_type, decoded_id = from_global_id(
                                            item["id"]
                                        )
                                        related_obj = field.related_model.objects.get(
                                            pk=decoded_id
                                        )
                                    except Exception:
                                        # If all else fails, raise the original error
                                        related_obj = field.related_model.objects.get(
                                            pk=item["id"]
                                        )

                                # If there are other fields besides 'id', update the object
                                update_data = {
                                    k: v for k, v in item.items() if k != "id"
                                }
                                if update_data:
                                    # Update the existing object with new data
                                    related_obj = self.handle_nested_update(
                                        field.related_model, item, related_obj
                                    )
                            else:
                                # Create new object from dict data
                                related_obj = self.handle_nested_create(
                                    field.related_model, item
                                )
                            related_objects.append(related_obj)
                        elif isinstance(item, str):
                            # Create new object with string as name
                            # Assume the model has a 'name' field for string values
                            name_field = getattr(
                                field.related_model, "_nested_name_field", "name"
                            )
                            related_obj = self.handle_nested_create(
                                field.related_model, {name_field: item}
                            )
                            related_objects.append(related_obj)
                        elif isinstance(item, (int, uuid.UUID)):
                            # Get existing object by ID
                            related_obj = field.related_model.objects.get(pk=item)
                            related_objects.append(related_obj)

                    # Replace all relationships with the new set
                    m2m_manager.set(related_objects)

            return instance

        except ValidationError as e:
            # Preserve field-specific errors so mutation can map them to fields
            raise e
        except IntegrityError as e:
            # Attempt to parse constraint violations and map to fields
            error_msg = str(e)

            # Handle not-null constraint violations (French message)
            match = re.search(r'null value in column "(\w+)".*violates not-null constraint', error_msg)
            if match:
                column_name = match.group(1)
                field_name = self._map_column_to_field(model, column_name) or column_name
                label = self._get_field_verbose_name(model, field_name) or field_name
                raise ValidationError({field_name: f"Le champ '{label}' ne peut pas être nul."})

            # Handle unique constraint violations (French message)
            fields = self._extract_unique_constraint_fields(model, e)
            if fields:
                return_errors = {}
                for field in fields:
                    label = self._get_field_verbose_name(model, field) or field
                    return_errors[field] = (
                        f"Doublon détecté: la valeur du champ '{label}' existe déjà. Veuillez fournir une valeur unique."
                    )
                raise ValidationError(return_errors)

            # Fallback to generic message in French if fields cannot be determined
            raise ValidationError(f"Échec de la mise à jour de {model.__name__} : {str(e)}")
        except Exception as e:
            # Wrap non-validation exceptions with context
            raise ValidationError(f"Failed to update {model.__name__}: {str(e)}")

    def _extract_unique_constraint_fields(
        self, model: Type[models.Model], error: Exception
    ) -> List[str]:
        """
        Extract field names from database integrity error messages for unique constraints.

        Supports common SQLite and PostgreSQL patterns. Returns model field names
        when possible; otherwise returns the DB column names.
        """
        msg = str(error)
        fields: List[str] = []

        # SQLite / generic pattern: UNIQUE constraint failed: app_model.field[, app_model.field]
        m = re.search(r"UNIQUE constraint failed: ([\w\., ]+)", msg)
        if m:
            cols = [part.strip() for part in m.group(1).split(",")]
            for col in cols:
                col_name = col.split(".")[-1]
                field_name = self._map_column_to_field(model, col_name) or col_name
                fields.append(field_name)

        # PostgreSQL pattern: Key (field[, field])=(value[, value]) already exists.
        if not fields:
            m2 = re.search(r"Key \(([^\)]+)\)=\(([^\)]+)\) already exists", msg)
            if m2:
                cols = [c.strip() for c in m2.group(1).split(",")]
                for col_name in cols:
                    field_name = self._map_column_to_field(model, col_name) or col_name
                    fields.append(field_name)

        return fields

    def _map_column_to_field(
        self, model: Type[models.Model], column: str
    ) -> Optional[str]:
        """
        Map a DB column name to the Django model field name.
        """
        try:
            for f in model._meta.get_fields():
                if hasattr(f, "column") and f.column == column:
                    return f.name
        except Exception:
            pass
        return None

    def _get_field_verbose_name(self, model: Type[models.Model], field_name: str) -> Optional[str]:
        """
        Retrieve the user-facing verbose_name for a Django field when available.

        Args:
            model: Django model class
            field_name: Name of the field in the Django model

        Returns:
            Optional[str]: The verbose_name string if available, otherwise None.
        """
        try:
            field = model._meta.get_field(field_name)
            # verbose_name can be lazy, cast to str for safety
            label = getattr(field, "verbose_name", None)
            if label:
                return str(label)
        except Exception:
            # If field lookup fails, return None to allow graceful fallback
            return None
        return None

    def handle_cascade_delete(
        self, instance: models.Model, cascade_rules: Optional[Dict[str, str]] = None
    ) -> List[str]:
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
                        f"Cannot delete {instance._meta.model_name} because it has related {field_name} objects"
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
        model: Type[models.Model],
        input_data: Dict[str, Any],
        operation: str = "create",
    ) -> List[str]:
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
                except:
                    continue  # Skip non-model fields

            return errors

        except Exception as e:
            return [f"Validation error: {str(e)}"]

    def _has_circular_reference(
        self,
        model: Type[models.Model],
        input_data: Dict[str, Any],
        visited_models: Optional[Set[Type[models.Model]]] = None,
    ) -> bool:
        """
        Checks for circular references in nested data.
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
                except:
                    continue

        return False

    def _validate_field_value(self, field: models.Field, value: Any) -> List[str]:
        """
        Validates a field value against field constraints.
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

    def _handle_reverse_relationships(
        self, instance: models.Model, input_data: Dict[str, Any]
    ) -> None:
        """
        Handle reverse relationships (e.g., creating comments for a post).

        Args:
            instance: The main instance that was just created
            input_data: The input data containing potential reverse relationship data
        """
        model = instance.__class__

        # Get all reverse relationships for this model
        reverse_relations = self._get_reverse_relations(model)

        for field_name, related_field in reverse_relations.items():
            if field_name not in input_data:
                continue

            value = input_data[field_name]
            if value is None:
                continue

            # Handle different types of reverse relationship data
            if isinstance(value, list):
                # List can contain either IDs (to connect existing objects) or dicts (to create new objects)
                for item in value:
                    if isinstance(item, dict):
                        # Create new object and set the foreign key to point to our instance
                        item[related_field.field.name] = instance.pk
                        self.handle_nested_create(related_field.related_model, item)
                    elif isinstance(item, (str, int)):
                        # Connect existing object to this instance
                        try:
                            related_field.related_model.objects.filter(pk=item).update(
                                **{related_field.field.name: instance}
                            )
                        except Exception as e:
                            raise ValidationError(
                                f"Failed to connect {related_field.related_model.__name__} with id {item}: {str(e)}"
                            )

            elif isinstance(value, dict):
                # Handle operations like create, connect, disconnect
                if "create" in value:
                    create_data = value["create"]
                    if isinstance(create_data, list):
                        for item in create_data:
                            if isinstance(item, dict):
                                # Set the foreign key to point to our instance
                                item[related_field.field.name] = instance.pk
                                self.handle_nested_create(
                                    related_field.related_model, item
                                )
                    elif isinstance(create_data, dict):
                        # Single object to create
                        create_data[related_field.field.name] = instance.pk
                        self.handle_nested_create(
                            related_field.related_model, create_data
                        )

                if "connect" in value:
                    # Connect existing objects to this instance
                    connect_ids = value["connect"]
                    if isinstance(connect_ids, list):
                        related_field.related_model.objects.filter(
                            pk__in=connect_ids
                        ).update(**{related_field.field.name: instance})

    def _get_reverse_relations(self, model: Type[models.Model]) -> Dict[str, Any]:
        """
        Get reverse relationships for a model.

        Args:
            model: The Django model to get reverse relations for

        Returns:
            Dict mapping field names to related field objects
        """
        reverse_relations = {}

        # Use the modern Django approach
        if hasattr(model._meta, "related_objects"):
            for rel in model._meta.related_objects:
                if hasattr(rel, "get_accessor_name"):
                    accessor_name = rel.get_accessor_name()
                else:
                    accessor_name = (
                        rel.related_name or f"{rel.related_model._meta.model_name}_set"
                    )

                # Only include if it should be included based on field rules
                if self._should_include_reverse_field(rel):
                    reverse_relations[accessor_name] = rel

        # For modern Django versions, use related_objects
        if hasattr(model._meta, "related_objects"):
            for rel in model._meta.related_objects:
                accessor_name = rel.get_accessor_name()
                if self._should_include_reverse_field(rel):
                    reverse_relations[accessor_name] = rel

        # Fallback for Django versions that use get_fields() with related fields
        elif hasattr(model._meta, "get_fields"):
            try:
                for field in model._meta.get_fields():
                    # Check if it's a reverse relation (ForeignKey, OneToOneField, ManyToManyField)
                    if hasattr(field, "related_model") and hasattr(
                        field, "get_accessor_name"
                    ):
                        if self._should_include_reverse_field(field):
                            accessor_name = field.get_accessor_name()
                            reverse_relations[accessor_name] = field
            except AttributeError:
                # If get_fields doesn't work as expected, continue without reverse relations
                pass

        # Final fallback for very old Django versions
        elif hasattr(model._meta, "get_all_related_objects"):
            for rel in model._meta.get_all_related_objects():
                accessor_name = rel.get_accessor_name()
                if self._should_include_reverse_field(rel):
                    reverse_relations[accessor_name] = rel

        return reverse_relations

    def _should_include_reverse_field(self, rel) -> bool:
        """
        Determine if a reverse relationship field should be included.

        Args:
            rel: The relationship object

        Returns:
            bool: True if the field should be included
        """
        # Skip if it's a many-to-many through relationship
        if (
            hasattr(rel, "through")
            and rel.through
            and not rel.through._meta.auto_created
        ):
            return False

        # Skip if it's marked as hidden
        if hasattr(rel, "hidden") and rel.hidden:
            return False

        # Skip if the related model is abstract
        if hasattr(rel, "related_model") and rel.related_model._meta.abstract:
            return False

        return True

    def _process_nested_fields(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process nested_ prefixed fields and extract them to their corresponding model fields.

        Args:
            input_data: Raw input data containing nested_ prefixed fields

        Returns:
            Processed input data with nested_ fields extracted and mapped
        """
        processed_data = {}

        for field_name, value in input_data.items():
            if field_name.startswith("nested_"):
                # Extract the actual field name (remove 'nested_' prefix)
                actual_field_name = field_name[7:]  # Remove 'nested_' prefix

                # If the actual field already exists in input, prioritize nested_ version
                if actual_field_name in input_data:
                    # Log warning about conflicting fields
                    logger.warning(
                        f"Both '{field_name}' and '{actual_field_name}' provided. "
                        f"Using nested field '{field_name}'"
                    )

                # Map nested field to actual field name
                processed_data[actual_field_name] = value
            else:
                # Only add non-nested field if no nested version exists
                nested_field_name = f"nested_{field_name}"
                if nested_field_name not in input_data:
                    processed_data[field_name] = value

        return processed_data
