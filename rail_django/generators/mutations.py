"""
Mutation Generation System for Django GraphQL Auto-Generation

This module provides the MutationGenerator class, which is responsible for creating
GraphQL mutations for Django models, including CRUD operations and custom method mutations.
"""

from .types import TypeGenerator
from .nested_operations import NestedOperationHandler
from .introspector import MethodInfo, ModelIntrospector
from ..core.settings import MutationGeneratorSettings
from ..core.meta import get_model_graphql_meta
from ..core.security import get_auth_manager, get_authz_manager, get_input_validator
from ..core.performance import get_query_optimizer
from ..core.error_handling import get_error_handler
from ..conf import get_mutation_generator_settings
import inspect
import re
from typing import Any, Callable, Dict, List, Optional, Type, Union, get_origin

import graphene
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from graphene_django import DjangoObjectType
from graphene.types.generic import GenericScalar


class MutationError(graphene.ObjectType):
    """
    Structured error type for GraphQL mutations.

    Attributes:
        field: The field name where the error occurred (optional)
        message: The error message describing what went wrong
    """

    field = graphene.String(description="Le nom du champ où l'erreur s'est produite")
    message = graphene.String(
        required=False,
        description="Le message d'erreur décrivant ce qui s'est mal passé",
    )


def _normalize_field_path(field: Any, prefix: Optional[str] = None) -> Optional[str]:
    """
    Convert backend field identifiers (including dotted, double-underscore or list
    index notations) to a consistent dot-separated path understood by the frontend.
    """
    if field is None:
        return prefix

    segment = str(field)
    segment = segment.replace("__", ".")
    segment = segment.replace("[", ".").replace("]", "")
    segment = segment.replace("..", ".").strip(".")
    if prefix:
        return f"{prefix}.{segment}".strip(".")
    return segment or None


def _flatten_validation_error(
    detail: Any, path: Optional[str], accumulator: List[MutationError]
) -> None:
    """
    Recursively flatten Django ValidationError payloads (dict/list/ValidationError)
    into a flat list of MutationError objects with normalized field paths.
    """
    if isinstance(detail, ValidationError):
        if hasattr(detail, "message_dict") and isinstance(detail.message_dict, dict):
            for field_name, messages in detail.message_dict.items():
                next_path = _normalize_field_path(field_name, path)
                _flatten_validation_error(messages, next_path, accumulator)
            return
        if hasattr(detail, "error_dict") and isinstance(detail.error_dict, dict):
            for field_name, messages in detail.error_dict.items():
                next_path = _normalize_field_path(field_name, path)
                _flatten_validation_error(messages, next_path, accumulator)
            return
        messages = (
            detail.messages
            if hasattr(detail, "messages") and isinstance(detail.messages, list)
            else [str(detail)]
        )
        for message in messages:
            accumulator.append(MutationError(field=path, message=str(message)))
        return

    if isinstance(detail, dict):
        for field_name, messages in detail.items():
            next_path = _normalize_field_path(field_name, path)
            _flatten_validation_error(messages, next_path, accumulator)
        return

    if isinstance(detail, (list, tuple)):
        for index, item in enumerate(detail):
            next_path = path
            if isinstance(item, (dict, list, ValidationError)):
                next_path = _normalize_field_path(index, path)
            _flatten_validation_error(item, next_path, accumulator)
        return

    accumulator.append(MutationError(field=path, message=str(detail)))


def build_validation_errors(
    error: ValidationError, prefix: Optional[str] = None
) -> List[MutationError]:
    """Convert a ValidationError into a flat list of MutationError objects."""
    collected: List[MutationError] = []
    _flatten_validation_error(error, prefix, collected)
    return collected


def build_mutation_error(message: str, field: Optional[str] = None) -> MutationError:
    """Helper to build a single MutationError with a normalized field path."""
    return MutationError(field=_normalize_field_path(field), message=str(message))


class MutationGenerator:
    """
    Creates GraphQL mutations for Django models, supporting CRUD operations
    and custom method-based mutations.

    This class supports:
    - CRUD operations (Create, Read, Update, Delete)
    - Bulk operations for multiple records
    - Nested operations for related models
    - Security and authorization integration
    - Input validation and error handling
    - Performance optimization
    """

    def __init__(
        self,
        type_generator: TypeGenerator,
        settings: Optional[MutationGeneratorSettings] = None,
        schema_name: str = "default",
    ):
        """
        Initialize the MutationGenerator.

        Args:
            type_generator: TypeGenerator instance for creating GraphQL types
            settings: Mutation generator settings or None for defaults
            schema_name: Name of the schema for multi-schema support
        """
        self.type_generator = type_generator
        self.schema_name = schema_name

        # Use hierarchical settings if no explicit settings provided
        if settings is None:
            self.settings = MutationGeneratorSettings.from_schema(schema_name)
        else:
            self.settings = settings

        # Initialize security and performance components
        self.authentication_manager = get_auth_manager(schema_name)
        self.authorization_manager = get_authz_manager(schema_name)
        self.input_validator = get_input_validator(schema_name)
        self.error_handler = get_error_handler(schema_name)
        self.query_optimizer = get_query_optimizer(schema_name)

        # Pass mutation settings to type generator for nested relations configuration
        self.type_generator.mutation_settings = self.settings
        self._mutation_classes: Dict[str, Type[graphene.Mutation]] = {}
        self.nested_handler = NestedOperationHandler(self.settings)

    def generate_create_mutation(
        self, model: Type[models.Model]
    ) -> Type[graphene.Mutation]:
        """
        Generates a mutation for creating a new model instance.
        Supports nested creates for related objects.
        """
        model_type = self.type_generator.generate_object_type(model)
        input_type = self.type_generator.generate_input_type(
            model, mutation_type="create"
        )
        model_name = model.__name__
        graphql_meta = get_model_graphql_meta(model)
        graphql_meta = get_model_graphql_meta(model)
        graphql_meta = get_model_graphql_meta(model)
        read_only_fields = set(
            getattr(graphql_meta.field_config, "read_only", []) or []
        )

        class CreateMutation(graphene.Mutation):
            class Arguments:
                input = input_type(required=True)

            # Standardized return type
            ok = graphene.Boolean()
            object = graphene.Field(model_type)
            errors = graphene.List(MutationError)

            @classmethod
            @transaction.atomic
            def mutate(
                cls, root: Any, info: graphene.ResolveInfo, input: Dict[str, Any]
            ) -> "CreateMutation":
                try:
                    graphql_meta.ensure_operation_access("create", info=info)
                    # Handle double quotes in string fields
                    input = cls._sanitize_input_data(input)

                    # Normalize enum inputs (GraphQL Enum -> underlying Django values)
                    input = cls._normalize_enum_inputs(input, model)

                    # Process dual fields with automatic priority handling
                    input = cls._process_dual_fields(input, model)
                    if read_only_fields:
                        input = {
                            key: value
                            for key, value in input.items()
                            if key not in read_only_fields
                        }

                    # Use the nested operation handler for advanced nested operations
                    nested_handler = cls._get_nested_handler(info)

                    # Validate nested data before processing
                    validation_errors = nested_handler.validate_nested_data(
                        model, input, "create"
                    )
                    if validation_errors:
                        return cls(ok=False, object=None, errors=validation_errors)

                    # Handle nested create with comprehensive validation and transaction management
                    instance = nested_handler.handle_nested_create(model, input)

                    return cls(ok=True, object=instance, errors=None)

                except ValidationError as exc:
                    error_objects = build_validation_errors(exc)
                    return cls(ok=False, object=None, errors=error_objects)
                except IntegrityError as exc:
                    transaction.set_rollback(True)
                    error_msg = str(exc)
                    match = re.search(
                        r'null value in column "(\w+)".*violates not-null constraint',
                        error_msg,
                    )
                    if match:
                        field_name = match.group(1)
                        error_objects = [
                            build_mutation_error(
                                message=f"{field_name} cannot be null.", field=field_name
                            )
                        ]
                    else:
                        error_objects = [
                            build_mutation_error(
                                message=f"Database integrity error: {error_msg}"
                            )
                        ]
                    return cls(ok=False, object=None, errors=error_objects)
                except Exception as exc:
                    transaction.set_rollback(True)
                    error_objects = [
                        build_mutation_error(
                            message=f"Failed to create {model_name}: {str(exc)}"
                        )
                    ]
                    return cls(ok=False, object=None, errors=error_objects)

            @classmethod
            def _sanitize_input_data(cls, input_data: Dict[str, Any]) -> Dict[str, Any]:
                """
                Sanitize input data to handle double quotes and other special characters.

                Args:
                    input_data: The input data to sanitize

                Returns:
                    Dict with sanitized data
                """
                # Ensure ID is a string if present (handles UUID objects)
                if "id" in input_data and not isinstance(input_data["id"], str):
                    input_data["id"] = str(input_data["id"])

                def sanitize_value(value):
                    if isinstance(value, str):
                        # Handle double quotes by escaping them properly
                        return value.replace('""', '"')
                    elif isinstance(value, dict):
                        return {k: sanitize_value(v) for k, v in value.items()}
                    elif isinstance(value, list):
                        return [sanitize_value(item) for item in value]
                    return value

                return {k: sanitize_value(v) for k, v in input_data.items()}

            @classmethod
            def _normalize_enum_inputs(
                cls, input_data: Dict[str, Any], model: Type[models.Model]
            ) -> Dict[str, Any]:
                """
                Purpose: Normalize GraphQL Enum inputs to their underlying Django field values.
                Args:
                    input_data: Input payload from GraphQL mutation
                    model: Django model being mutated
                Returns:
                    Dict: Input data with enum values normalized
                Raises:
                    None
                Example:
                    >>> normalized = CreateMutation._normalize_enum_inputs({'status': SomeEnum.ACTIVE}, Book)
                    >>> isinstance(normalized['status'], str)
                    True
                """
                normalized: Dict[str, Any] = input_data.copy()

                # Build mapping of choice fields for the model
                choice_fields = {
                    f.name: f
                    for f in model._meta.get_fields()
                    if hasattr(f, "choices") and getattr(f, "choices", None)
                }

                def normalize_value(value: Any) -> Any:
                    # Graphene enum may come through as an object with a 'value' attribute
                    if hasattr(value, "value") and not isinstance(value, (str, bytes)):
                        try:
                            return getattr(value, "value")
                        except Exception:
                            return value
                    # Recurse into lists/dicts for nested structures
                    if isinstance(value, list):
                        return [normalize_value(v) for v in value]
                    if isinstance(value, dict):
                        return {k: normalize_value(v) for k, v in value.items()}
                    return value

                for field_name in choice_fields.keys():
                    if field_name in normalized:
                        normalized[field_name] = normalize_value(normalized[field_name])

                return normalized

            @classmethod
            def _process_dual_fields(
                cls, input_data: Dict[str, Any], model: Type[models.Model]
            ) -> Dict[str, Any]:
                """
                Process dual fields with automatic priority handling and validation.

                For OneToManyRel (ForeignKey, OneToOneField):
                - Validates mutual exclusivity: only one of nested_<field_name> or <field_name> should be provided
                - Enforces mandatory fields: ensures required fields have either direct or nested value
                - If both nested_<field_name> and <field_name> are provided, raises ValidationError

                For ManyToManyRel:
                - If nested_<field_name> is provided, create nested objects first and merge their IDs
                  into the direct assign data (<field_name>: [ID])

                Args:
                    input_data: The input data to process
                    model: The Django model

                Returns:
                    Dict with processed dual fields

                Raises:
                    ValidationError: If mutual exclusivity is violated or mandatory fields are missing
                """
                processed_data = input_data.copy()

                # Get model relationships
                introspector = ModelIntrospector(model)
                relationships = introspector.get_model_relationships()

                # Define mandatory fields that require either direct or nested value
                mandatory_fields = cls._get_mandatory_fields(model)

                for field_name, rel_info in relationships.items():
                    nested_field_name = f"nested_{field_name}"

                    if rel_info.relationship_type in ["ForeignKey", "OneToOneField"]:
                        # Check for mutual exclusivity violation
                        if (
                            nested_field_name in processed_data
                            and field_name in processed_data
                        ):
                            raise ValidationError(
                                {
                                    field_name: f"Cannot provide both '{field_name}' and '{nested_field_name}'. Please provide only one."
                                }
                            )

                        # Check if mandatory field is missing
                        if field_name in mandatory_fields:
                            if (
                                nested_field_name not in processed_data
                                and field_name not in processed_data
                            ):
                                raise ValidationError(
                                    {
                                        field_name: f"Field '{field_name}' is mandatory. Please provide either '{field_name}' or '{nested_field_name}'."
                                    }
                                )

                        # Transform nested field to direct field for processing
                        if nested_field_name in processed_data:
                            # Transform nested field name to direct field name
                            processed_data[field_name] = processed_data.pop(
                                nested_field_name
                            )

                    elif rel_info.relationship_type == "ManyToManyField":
                        # ManyToManyRel: Create nested objects first, then merge IDs
                        if nested_field_name in processed_data:
                            nested_data = processed_data.pop(nested_field_name)

                            # For now, transform nested field to direct field for processing
                            # The nested operation handler will handle the actual creation
                            processed_data[field_name] = nested_data

                # Handle reverse relationships (e.g., comments for Post)
                reverse_relations = introspector.get_reverse_relations()
                for field_name, related_model in reverse_relations.items():
                    nested_field_name = f"nested_{field_name}"

                    if nested_field_name in processed_data:
                        # Transform nested field name to direct field name
                        processed_data[field_name] = processed_data.pop(
                            nested_field_name
                        )

                return processed_data

            @classmethod
            def _get_mandatory_fields(cls, model: Type[models.Model]) -> List[str]:
                """
                Get list of mandatory fields for the given model.

                Args:
                    model: The Django model

                Returns:
                    List of field names that are mandatory
                """
                # Define mandatory fields per model
                # This can be extended to read from model metadata or configuration
                mandatory_fields_map = {
                    "BlogPost": ["category"],
                    # Add other models and their mandatory fields here
                }

                model_name = model.__name__
                return mandatory_fields_map.get(model_name, [])

            @classmethod
            def _get_nested_handler(
                cls, info: graphene.ResolveInfo
            ) -> NestedOperationHandler:
                """Get the nested operation handler from the mutation generator."""
                # Access the mutation generator through the schema context
                if hasattr(info.context, "mutation_generator"):
                    return info.context.mutation_generator.nested_handler
                # Fallback to creating a new handler
                return NestedOperationHandler()

        return type(
            f"Create{model_name}",
            (CreateMutation,),
            {"__doc__": f"Create a new {model_name} instance"},
        )

    def generate_update_mutation(
        self, model: Type[models.Model]
    ) -> Type[graphene.Mutation]:
        """
        Generates a mutation for updating an existing model instance.
        Supports partial updates and nested updates for related objects.
        """
        model_type = self.type_generator.generate_object_type(model)
        input_type = self.type_generator.generate_input_type(
            model, partial=True, mutation_type="update"
        )
        model_name = model.__name__
        graphql_meta = get_model_graphql_meta(model)
        read_only_fields = set(
            getattr(graphql_meta.field_config, "read_only", []) or []
        )

        class UpdateMutation(graphene.Mutation):
            class Arguments:
                input = input_type(required=True)

            # Standardized return type
            ok = graphene.Boolean()
            object = graphene.Field(model_type)
            errors = graphene.List(MutationError)

            @classmethod
            @transaction.atomic
            def mutate(
                cls,
                root: Any,
                info: graphene.ResolveInfo,
                input: Dict[str, Any],
            ) -> "UpdateMutation":
                try:
                    input = cls._sanitize_input_data(input)
                    record_id = input.get("id")
                    if not record_id:
                        return cls(
                            ok=False,
                            object=None,
                            errors=[
                                MutationError(
                                    field="id",
                                    message="L'identifiant est requis pour la mise à jour.",
                                )
                            ],
                        )

                    # Remove id from the update payload to avoid attempting to overwrite PK
                    update_data = {
                        key: value for key, value in input.items() if key != "id"
                    }

                    # Normalize enum inputs (GraphQL Enum -> underlying Django values)
                    update_data = cls._normalize_enum_inputs(update_data, model)

                    # Process dual fields with automatic priority handling
                    update_data = cls._process_dual_fields(update_data, model)
                    if read_only_fields:
                        update_data = {
                            key: value
                            for key, value in update_data.items()
                            if key not in read_only_fields
                        }

                    # Decode GraphQL ID to database ID if needed
                    try:
                        # Try to use the ID as-is first (for integer IDs)
                        instance = model.objects.get(pk=record_id)
                    except (ValueError, model.DoesNotExist):
                        # If that fails, try to decode as GraphQL global ID
                        from graphql_relay import from_global_id

                        try:
                            decoded_type, decoded_id = from_global_id(record_id)
                            instance = model.objects.get(pk=decoded_id)
                        except Exception:
                            # If all else fails, raise the original error
                            instance = model.objects.get(pk=record_id)

                    graphql_meta.ensure_operation_access(
                        "update", info=info, instance=instance
                    )

                    # Use the nested operation handler for advanced nested operations
                    nested_handler = cls._get_nested_handler(info)

                    # Validate nested data before processing
                    validation_errors = nested_handler.validate_nested_data(
                        model, update_data, "update"
                    )
                    if validation_errors:
                        return cls(ok=False, object=None, errors=validation_errors)

                    # Handle nested update with comprehensive validation and transaction management
                    instance = nested_handler.handle_nested_update(
                        model, update_data, instance
                    )

                    return UpdateMutation(ok=True, object=instance, errors=[])

                except model.DoesNotExist:
                    error_objects = [
                        build_mutation_error(
                            message=f"{model_name} with id {record_id} does not exist"
                        )
                    ]
                    return UpdateMutation(ok=False, object=None, errors=error_objects)
                except ValidationError as exc:
                    error_objects = build_validation_errors(exc)
                    return UpdateMutation(ok=False, object=None, errors=error_objects)
                except IntegrityError as exc:
                    transaction.set_rollback(True)
                    error_msg = str(exc)
                    match = re.search(
                        r'null value in column "(\w+)".*violates not-null constraint',
                        error_msg,
                    )
                    if match:
                        field_name = match.group(1)
                        error_objects = [
                            build_mutation_error(
                                message=f"{field_name} cannot be null.", field=field_name
                            )
                        ]
                    else:
                        error_objects = [
                            build_mutation_error(
                                message=f"Database integrity error: {error_msg}"
                            )
                        ]
                    return UpdateMutation(ok=False, object=None, errors=error_objects)
                except Exception as exc:
                    transaction.set_rollback(True)
                    error_objects = [
                        build_mutation_error(
                            message=f"Failed to update {model_name}: {str(exc)}"
                        )
                    ]
                    return UpdateMutation(ok=False, object=None, errors=error_objects)
            @classmethod
            def _sanitize_input_data(cls, input_data: Dict[str, Any]) -> Dict[str, Any]:
                """
                Sanitize input data to handle double quotes and other special characters.

                Args:
                    input_data: The input data to sanitize

                Returns:
                    Dict with sanitized data
                """
                # Ensure ID is a string if present (handles UUID objects)
                if "id" in input_data and not isinstance(input_data["id"], str):
                    input_data["id"] = str(input_data["id"])

                def sanitize_value(value):
                    if isinstance(value, str):
                        # Handle double quotes by escaping them properly
                        return value.replace('""', '"')
                    elif isinstance(value, dict):
                        return {k: sanitize_value(v) for k, v in value.items()}
                    elif isinstance(value, list):
                        return [sanitize_value(item) for item in value]
                    return value

                return {k: sanitize_value(v) for k, v in input_data.items()}

            @classmethod
            def _normalize_enum_inputs(
                cls, input_data: Dict[str, Any], model: Type[models.Model]
            ) -> Dict[str, Any]:
                """
                Purpose: Normalize GraphQL Enum inputs to their underlying Django field values for updates.
                Args:
                    input_data: Input payload from GraphQL mutation
                    model: Django model being mutated
                Returns:
                    Dict: Input data with enum values normalized
                Raises:
                    None
                Example:
                    >>> normalized = UpdateMutation._normalize_enum_inputs({'status': SomeEnum.ACTIVE}, Book)
                    >>> isinstance(normalized['status'], str)
                    True
                """
                normalized: Dict[str, Any] = input_data.copy()

                # Build mapping of choice fields for the model
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

                for field_name in choice_fields.keys():
                    if field_name in normalized:
                        normalized[field_name] = normalize_value(normalized[field_name])

                return normalized

            @classmethod
            def _process_dual_fields(
                cls, input_data: Dict[str, Any], model: Type[models.Model]
            ) -> Dict[str, Any]:
                """
                Process dual fields with automatic priority handling and validation.

                For OneToManyRel (ForeignKey, OneToOneField):
                - Validates mutual exclusivity: only one of field or nested_field should be provided
                - Validates mandatory fields: ensures required fields have either direct or nested value
                - If both nested_<field_name> and <field_name> are provided, raises ValidationError

                For ManyToManyRel:
                - If nested_<field_name> is provided, create nested objects first and merge their IDs
                  into the direct assign data (<field_name>: [ID])

                Args:
                    input_data: The input data to process
                    model: The Django model

                Returns:
                    Dict with processed dual fields

                Raises:
                    ValidationError: If mutual exclusivity or mandatory field rules are violated
                """
                processed_data = input_data.copy()

                # Get model relationships
                introspector = ModelIntrospector(model)
                relationships = introspector.get_model_relationships()

                # Get mandatory fields for this model
                mandatory_fields = cls._get_mandatory_fields(model)

                for field_name, rel_info in relationships.items():
                    nested_field_name = f"nested_{field_name}"

                    if rel_info.relationship_type in ["ForeignKey", "OneToOneField"]:
                        has_direct = (
                            field_name in processed_data
                            and processed_data[field_name] is not None
                        )
                        has_nested = (
                            nested_field_name in processed_data
                            and processed_data[nested_field_name] is not None
                        )

                        # Validate mutual exclusivity
                        if has_direct and has_nested:
                            raise ValidationError(
                                {
                                    field_name: f"Cannot provide both '{field_name}' and '{nested_field_name}'. Please provide only one."
                                }
                            )

                        # Validate mandatory fields
                        if (
                            field_name in mandatory_fields
                            and not has_direct
                            and not has_nested
                        ):
                            raise ValidationError(
                                {
                                    field_name: f"Field '{field_name}' is mandatory. Please provide either '{field_name}' or '{nested_field_name}'."
                                }
                            )

                        # OneToManyRel: Prioritize nested field over direct ID field
                        if has_nested:
                            # Transform nested field name to direct field name
                            processed_data[field_name] = processed_data.pop(
                                nested_field_name
                            )

                    elif rel_info.relationship_type == "ManyToManyField":
                        # ManyToManyRel: Create nested objects first, then merge IDs
                        if nested_field_name in processed_data:
                            nested_data = processed_data.pop(nested_field_name)

                            # For now, transform nested field to direct field for processing
                            # The nested operation handler will handle the actual creation
                            processed_data[field_name] = nested_data

                # Handle reverse relationships (e.g., comments for Post)
                reverse_relations = introspector.get_reverse_relations()
                for field_name, related_model in reverse_relations.items():
                    nested_field_name = f"nested_{field_name}"

                    if nested_field_name in processed_data:
                        # Transform nested field name to direct field name
                        processed_data[field_name] = processed_data.pop(
                            nested_field_name
                        )

                return processed_data

            @classmethod
            def _get_mandatory_fields(cls, model: Type[models.Model]) -> List[str]:
                """
                Get list of mandatory fields for the given model.
                Override this method to customize mandatory field requirements.

                Args:
                    model: The Django model class

                Returns:
                    List of field names that are mandatory
                """
                # For now, hardcode BlogPost category as mandatory
                # This should be made configurable in the future
                if model.__name__ == "BlogPost":
                    return ["category"]
                return []

            @classmethod
            def _get_nested_handler(
                cls, info: graphene.ResolveInfo
            ) -> NestedOperationHandler:
                """Get the nested operation handler from the mutation generator."""
                # Access the mutation generator through the schema context
                if hasattr(info.context, "mutation_generator"):
                    return info.context.mutation_generator.nested_handler
                # Fallback to creating a new handler
                return NestedOperationHandler()

        return type(
            f"Update{model_name}",
            (UpdateMutation,),
            {"__doc__": f"Update an existing {model_name} instance"},
        )

    def generate_delete_mutation(
        self, model: Type[models.Model]
    ) -> Type[graphene.Mutation]:
        """
        Generates a mutation for deleting a model instance.
        Supports cascade delete configuration.
        """
        model_type = self.type_generator.generate_object_type(model)
        model_name = model.__name__
        graphql_meta = get_model_graphql_meta(model)
        graphql_meta = get_model_graphql_meta(model)

        class DeleteMutation(graphene.Mutation):
            class Arguments:
                id = graphene.ID(required=True)

            # Standardized return type
            ok = graphene.Boolean()
            object = graphene.Field(model_type)
            errors = graphene.List(MutationError)

            @classmethod
            @transaction.atomic
            def mutate(
                cls, root: Any, info: graphene.ResolveInfo, id: str
            ) -> "DeleteMutation":
                try:
                    instance = model.objects.get(pk=id)
                    graphql_meta.ensure_operation_access(
                        "delete", info=info, instance=instance
                    )
                    deleted_instance = instance  # Store reference before deletion
                    instance.delete()
                    return cls(ok=True, object=deleted_instance, errors=[])

                except model.DoesNotExist:
                    error_objects = [
                        MutationError(
                            field=None,
                            message=f"{model_name} with id {id} does not exist",
                        )
                    ]
                    return cls(ok=False, object=None, errors=error_objects)
                except Exception as e:
                    transaction.set_rollback(True)
                    error_objects = [
                        MutationError(
                            field=None,
                            message=f"Failed to delete {model_name}: {str(e)}",
                        )
                    ]
                    return cls(ok=False, object=None, errors=error_objects)

        return type(
            f"Delete{model_name}",
            (DeleteMutation,),
            {"__doc__": f"Delete a {model_name} instance"},
        )

    def generate_bulk_create_mutation(
        self, model: Type[models.Model]
    ) -> Type[graphene.Mutation]:
        """
        Generates a mutation for creating multiple model instances in bulk.
        """
        model_type = self.type_generator.generate_object_type(model)
        input_type = self.type_generator.generate_input_type(
            model, mutation_type="create"
        )
        model_name = model.__name__

        class BulkCreateMutation(graphene.Mutation):
            class Arguments:
                inputs = graphene.List(input_type, required=True)

            # Standardized return type
            ok = graphene.Boolean()
            objects = graphene.List(model_type)  # Using 'objects' for multiple items
            errors = graphene.List(MutationError)

            @classmethod
            @transaction.atomic
            def mutate(
                cls, root: Any, info: graphene.ResolveInfo, inputs: List[Dict[str, Any]]
            ) -> "BulkCreateMutation":
                try:
                    graphql_meta.ensure_operation_access("bulk_create", info=info)
                    instances = []
                    for input_data in inputs:
                        # Normalize enum inputs (GraphQL Enum -> underlying Django values)
                        input_data = cls._normalize_enum_inputs(input_data, model)
                        instance = model.objects.create(**input_data)
                        instances.append(instance)

                    return cls(ok=True, objects=instances, errors=[])

                except ValidationError as e:
                    # Create structured error objects for validation errors
                    error_objects = []
                    if hasattr(e, "error_dict"):
                        # Field-specific validation errors
                        for field, errors in e.error_dict.items():
                            for error in errors:
                                error_objects.append(
                                    MutationError(field=field, message=str(error))
                                )
                    else:
                        # General validation error
                        error_objects.append(MutationError(field=None, message=str(e)))
                    return cls(ok=False, objects=[], errors=error_objects)
                except IntegrityError as e:
                    transaction.set_rollback(True)
                    error_msg = str(e)
                    # Parse not-null constraint violation
                    match = re.search(
                        r'null value in column "(\w+)".*violates not-null constraint',
                        error_msg,
                    )
                    if match:
                        field_name = match.group(1)
                        error_objects = [
                            MutationError(
                                field=field_name,
                                message=f"{field_name} cannot be null.",
                            )
                        ]
                    else:
                        error_objects = [
                            MutationError(
                                field=None,
                                message=f"Database integrity error: {error_msg}",
                            )
                        ]
                    return cls(ok=False, objects=[], errors=error_objects)
                except Exception as e:
                    transaction.set_rollback(True)
                    error_objects = [
                        MutationError(
                            field=None,
                            message=f"Failed to bulk create {model_name}s: {str(e)}",
                        )
                    ]
                    return cls(ok=False, objects=[], errors=error_objects)

            @classmethod
            def _normalize_enum_inputs(
                cls, input_data: Dict[str, Any], model: Type[models.Model]
            ) -> Dict[str, Any]:
                """
                Purpose: Normalize GraphQL Enum inputs to their underlying Django field values for bulk create.
                Args:
                    input_data: Single input payload from GraphQL bulk mutation list
                    model: Django model being mutated
                Returns:
                    Dict: Input data with enum values normalized
                Raises:
                    None
                Example:
                    >>> normalized = BulkCreateMutation._normalize_enum_inputs({'status': SomeEnum.ACTIVE}, Book)
                    >>> isinstance(normalized['status'], str)
                    True
                """
                normalized: Dict[str, Any] = input_data.copy()

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

                for field_name in choice_fields.keys():
                    if field_name in normalized:
                        normalized[field_name] = normalize_value(normalized[field_name])

                return normalized

        return type(
            f"BulkCreate{model_name}",
            (BulkCreateMutation,),
            {"__doc__": f"Create multiple {model_name} instances"},
        )

    def generate_bulk_update_mutation(
        self, model: Type[models.Model]
    ) -> Type[graphene.Mutation]:
        """
        Generates a mutation for updating multiple model instances in bulk.
        """
        model_type = self.type_generator.generate_object_type(model)
        input_type = self.type_generator.generate_input_type(
            model, partial=True, mutation_type="update"
        )
        model_name = model.__name__

        class BulkUpdateInput(graphene.InputObjectType):
            id = graphene.ID(required=True)
            data = input_type(required=True)

        class BulkUpdateMutation(graphene.Mutation):
            class Arguments:
                inputs = graphene.List(BulkUpdateInput, required=True)

            # Standardized return type
            ok = graphene.Boolean()
            objects = graphene.List(model_type)  # Using 'objects' for multiple items
            errors = graphene.List(MutationError)

            @classmethod
            @transaction.atomic
            def mutate(
                cls, root: Any, info: graphene.ResolveInfo, inputs: List[Dict[str, Any]]
            ) -> "BulkUpdateMutation":
                try:
                    graphql_meta.ensure_operation_access("bulk_update", info=info)
                    instances = []
                    for input_data in inputs:
                        instance = model.objects.get(pk=input_data["id"])
                        graphql_meta.ensure_operation_access(
                            "bulk_update", info=info, instance=instance
                        )
                        # Normalize enum inputs for update payload
                        update_data = cls._normalize_enum_inputs(
                            input_data["data"], model
                        )
                        for field, value in update_data.items():
                            setattr(instance, field, value)
                        instance.full_clean()
                        instance.save()
                        instances.append(instance)

                    return cls(ok=True, objects=instances, errors=[])

                except model.DoesNotExist as exc:
                    return cls(
                        ok=False,
                        objects=[],
                        errors=[
                            build_mutation_error(
                                message=f"{model_name} not found: {str(exc)}"
                            )
                        ],
                    )
                except ValidationError as exc:
                    return cls(
                        ok=False, objects=[], errors=build_validation_errors(exc)
                    )
                except IntegrityError as exc:
                    transaction.set_rollback(True)
                    error_msg = str(exc)
                    match = re.search(
                        r'null value in column "(\w+)".*violates not-null constraint',
                        error_msg,
                    )
                    if match:
                        field_name = match.group(1)
                        error_objects = [
                            build_mutation_error(
                                message=f"{field_name} cannot be null.", field=field_name
                            )
                        ]
                    else:
                        error_objects = [
                            build_mutation_error(
                                message=f"Database integrity error: {error_msg}"
                            )
                        ]
                    return cls(ok=False, objects=[], errors=error_objects)
                except Exception as exc:
                    transaction.set_rollback(True)
                    return cls(
                        ok=False,
                        objects=[],
                        errors=[
                            build_mutation_error(
                                message=f"Failed to bulk update {model_name}s: {str(exc)}"
                            )
                        ],
                    )

        return type(
            f"BulkUpdate{model_name}",
            (BulkUpdateMutation,),
            {"__doc__": f"Update multiple {model_name} instances"},
        )

    def generate_bulk_delete_mutation(
        self, model: Type[models.Model]
    ) -> Type[graphene.Mutation]:
        """
        Generates a mutation for deleting multiple model instances in bulk.
        """
        model_type = self.type_generator.generate_object_type(model)
        model_name = model.__name__

        class BulkDeleteMutation(graphene.Mutation):
            class Arguments:
                ids = graphene.List(graphene.ID, required=True)

            # Standardized return type
            ok = graphene.Boolean()
            objects = graphene.List(model_type)  # Return deleted objects
            errors = graphene.List(MutationError)

            @classmethod
            @transaction.atomic
            def mutate(
                cls, root: Any, info: graphene.ResolveInfo, ids: List[str]
            ) -> "BulkDeleteMutation":
                try:
                    graphql_meta.ensure_operation_access("bulk_delete", info=info)
                    instances = model.objects.filter(pk__in=ids)
                    if len(instances) != len(ids):
                        found_ids = set(str(instance.pk) for instance in instances)
                        missing_ids = set(ids) - found_ids
                        return cls(
                            ok=False,
                            objects=[],
                            errors=[
                                build_mutation_error(
                                    message=f"Some {model_name} instances not found: {', '.join(missing_ids)}"
                                )
                            ],
                        )

                    deleted_instances = list(instances)  # Store before deletion
                    for inst in deleted_instances:
                        graphql_meta.ensure_operation_access(
                            "bulk_delete", info=info, instance=inst
                        )
                    instances.delete()
                    return cls(ok=True, objects=deleted_instances, errors=[])

                except model.DoesNotExist as exc:
                    return cls(
                        ok=False, objects=[], errors=[build_mutation_error(str(exc))]
                    )
                except Exception as exc:
                    transaction.set_rollback(True)
                    return cls(
                        ok=False,
                        objects=[],
                        errors=[
                            build_mutation_error(
                                message=f"Failed to bulk delete {model_name}s: {str(exc)}"
                            )
                        ],
                    )

        return type(
            f"BulkDelete{model_name}",
            (BulkDeleteMutation,),
            {"__doc__": f"Delete multiple {model_name} instances"},
        )

    def convert_method_to_mutation(
        self,
        model: Type[models.Model],
        method_name: str,
        custom_input_type: Optional[Type[graphene.InputObjectType]] = None,
        custom_output_type: Optional[Type[graphene.ObjectType]] = None,
    ) -> Optional[Type[graphene.Mutation]]:
        """
        Converts a model method to a GraphQL mutation with enhanced capabilities.

        Args:
            model: The Django model class
            method_name: Name of the method to convert
            custom_input_type: Optional custom input type
            custom_output_type: Optional custom output type

        Returns:
            GraphQL mutation class or None if method not found
        """
        if not hasattr(model, method_name):
            return None

        method = getattr(model, method_name)
        if not callable(method):
            return None

        signature = inspect.signature(method)
        model_name = model.__name__

        # Create input type
        if custom_input_type:
            input_type = custom_input_type
        else:
            input_fields = {}
            for param_name, param in signature.parameters.items():
                if param_name == "self":
                    continue

                param_type = (
                    param.annotation
                    if param.annotation != inspect.Parameter.empty
                    else Any
                )
                graphql_type = self._convert_python_type_to_graphql(param_type)

                if param.default == inspect.Parameter.empty:
                    input_fields[param_name] = graphql_type(required=True)
                else:
                    input_fields[param_name] = graphql_type(default_value=param.default)

            input_type = (
                type(
                    f"{model_name}{method_name.title()}Input",
                    (graphene.InputObjectType,),
                    input_fields,
                )
                if input_fields
                else None
            )

        # Determine output type
        if custom_output_type:
            output_type = custom_output_type
        else:
            return_type = signature.return_annotation
            if return_type == inspect.Parameter.empty:
                output_type = graphene.Boolean
            elif return_type == dict:
                output_type = graphene.JSONString
            else:
                output_type = self._convert_python_type_to_graphql(return_type)

        class ConvertedMethodMutation(graphene.Mutation):
            class Arguments:
                id = graphene.ID(required=True)

            # Standardized return format
            ok = graphene.Boolean()
            result = output_type()
            errors = graphene.List(MutationError)

            @classmethod
            @transaction.atomic
            def mutate(cls, root: Any, info: graphene.ResolveInfo, id: str, **kwargs):
                try:
                    # Check permissions if required
                    if hasattr(method, "_requires_permission"):
                        permission = method._requires_permission
                        if hasattr(info, "context") and hasattr(info.context, "user"):
                            if not info.context.user.has_perm(permission):
                                return cls(
                                    ok=False,
                                    result=None,
                                    errors=[build_mutation_error("Permission denied")],
                                )
                        else:
                            return cls(
                                ok=False,
                                result=None,
                                errors=[
                                    build_mutation_error("Authentication required")
                                ],
                            )

                    instance = model.objects.get(pk=id)
                    method_func = getattr(instance, method_name)

                    # Filter kwargs to only include method parameters
                    method_params = set(signature.parameters.keys()) - {"self"}
                    filtered_kwargs = {
                        k: v for k, v in kwargs.items() if k in method_params
                    }

                    # Execute method with filtered arguments
                    result = method_func(**filtered_kwargs)

                    # Handle model instance results
                    if isinstance(result, models.Model):
                        result.save()

                    return cls(ok=True, result=result, errors=[])

                except model.DoesNotExist:
                    return cls(
                        ok=False,
                        result=None,
                        errors=[
                            build_mutation_error(
                                message=f"{model_name} with id {id} does not exist"
                            )
                        ],
                    )
                except Exception as exc:
                    transaction.set_rollback(True)
                    return cls(
                        ok=False,
                        result=None,
                        errors=[
                            build_mutation_error(
                                message=f"Failed to execute {method_name}: {str(exc)}"
                            )
                        ],
                    )

        # Add method parameters as individual arguments
        for param_name, param in signature.parameters.items():
            if param_name == "self":
                continue

            param_type = (
                param.annotation if param.annotation != inspect.Parameter.empty else Any
            )
            graphql_type = self._convert_python_type_to_graphql(param_type)

            if param.default == inspect.Parameter.empty:
                setattr(
                    ConvertedMethodMutation.Arguments,
                    param_name,
                    graphql_type(required=True),
                )
            else:
                setattr(
                    ConvertedMethodMutation.Arguments,
                    param_name,
                    graphql_type(default_value=param.default),
                )

        # Preserve decorator metadata
        mutation_attrs = {
            "__doc__": method.__doc__ or f"Execute {method_name} on {model_name}"
        }

        # Check for business_logic decorator metadata
        if hasattr(method, "_business_logic_category"):
            mutation_attrs["_business_logic_category"] = method._business_logic_category
        if hasattr(method, "_requires_permission"):
            mutation_attrs["_requires_permission"] = method._requires_permission
        if hasattr(method, "_custom_mutation_name"):
            mutation_attrs["_custom_mutation_name"] = method._custom_mutation_name

        return type(
            f"{model_name}{method_name.title()}Mutation",
            (ConvertedMethodMutation,),
            mutation_attrs,
        )

    def _convert_python_type_to_graphql(
        self, python_type: Any
    ) -> Type[graphene.Scalar]:
        """
        Converts Python types to GraphQL types with enhanced mapping.

        Args:
            python_type: Python type annotation

        Returns:
            Corresponding GraphQL type
        """
        if isinstance(python_type, str):
            normalized = (
                python_type.replace("typing.", "").replace("builtins.", "").strip()
            )
            base = normalized.split("[", 1)[0].strip()
            if base.lower() in {"dict", "mapping"}:
                python_type = dict
            elif base.lower() in {"list", "tuple", "set"}:
                python_type = list
            elif base == "str":
                python_type = str
            elif base == "int":
                python_type = int
            elif base == "float":
                python_type = float
            elif base == "bool":
                python_type = bool
            elif base in {"Any", "object"}:
                python_type = Any
            elif base in {"None", "NoneType"}:
                python_type = type(None)

        origin = get_origin(python_type)
        if origin is dict:
            python_type = dict
        elif origin in {list, tuple, set}:
            python_type = list
        elif origin is Union:
            args = getattr(python_type, "__args__", ())
            non_none_types = [arg for arg in args if arg is not type(None)]
            if non_none_types:
                return self._convert_python_type_to_graphql(non_none_types[0])

        type_mapping = {
            str: graphene.String,
            int: graphene.Int,
            float: graphene.Float,
            bool: graphene.Boolean,
            dict: GenericScalar,
            list: GenericScalar,
            Any: GenericScalar,
            type(None): graphene.String,
        }

        # Handle Union types (e.g., Optional[str])
        if hasattr(python_type, "__origin__"):
            if python_type.__origin__ is Union:
                # For Optional types, use the non-None type
                args = python_type.__args__
                non_none_types = [arg for arg in args if arg is not type(None)]
                if non_none_types:
                    return self._convert_python_type_to_graphql(non_none_types[0])

        return type_mapping.get(python_type, graphene.String)

    def generate_method_mutation(
        self, model: Type[models.Model], method_info: MethodInfo
    ) -> Optional[Type[graphene.Mutation]]:
        """
        Generates a mutation from a model method.
        Analyzes method signature and return type to create appropriate mutation.
        Supports custom business logic and decorator-enhanced methods.
        """
        if not self.settings.enable_method_mutations:
            return None
        method_name = method_info.name
        method = getattr(model, method_name)
        signature = inspect.signature(method)
        model_name = model.__name__

        # Check for custom input/output types from decorators
        custom_input_type = getattr(method, "_mutation_input_type", None)
        custom_output_type = getattr(method, "_mutation_output_type", None)
        custom_name = getattr(method, "_custom_mutation_name", None)
        description = getattr(method, "_mutation_description", method.__doc__)
        is_business_logic = getattr(method, "_is_business_logic", False)
        requires_permissions = getattr(method, "_requires_permissions", None)
        if requires_permissions is None:
            legacy_perm = getattr(method, "_requires_permission", None)
            requires_permissions = [legacy_perm] if legacy_perm else None
        atomic = getattr(method, "_atomic", True)
        action_kind = getattr(method, "_action_kind", None)

        # Create input type for method arguments
        if custom_input_type:
            input_type = custom_input_type
        elif action_kind == "confirm":
            input_type = None
        else:
            input_fields = {}
            for param_name, param in signature.parameters.items():
                if param_name == "self":
                    continue

                param_type = (
                    param.annotation
                    if param.annotation != inspect.Parameter.empty
                    else Any
                )
                graphql_type = self._convert_python_type_to_graphql(param_type)

                if param.default == inspect.Parameter.empty:
                    input_fields[param_name] = graphql_type(required=True)
                else:
                    input_fields[param_name] = graphql_type(default_value=param.default)

            input_type = (
                type(
                    f"{model_name}{method_name.title()}Input",
                    (graphene.InputObjectType,),
                    input_fields,
                )
                if input_fields
                else None
            )

        # Determine return type
        if custom_output_type:
            output_type = custom_output_type
        else:
            return_type = signature.return_annotation
            if return_type == inspect.Parameter.empty:
                output_type = graphene.Boolean
            else:
                output_type = self._convert_python_type_to_graphql(return_type)

        class MethodMutation(graphene.Mutation):
            class Arguments:
                id = graphene.ID(required=True)
                if input_type:
                    input = input_type(required=True)

            # Standardized return format
            ok = graphene.Boolean()
            result = output_type()
            errors = graphene.List(MutationError)

            @classmethod
            def mutate(
                cls,
                root: Any,
                info: graphene.ResolveInfo,
                id: str,
                input: Dict[str, Any] = None,
            ):
                # Permission check if required
                if requires_permissions and hasattr(info.context, "user"):
                    user = info.context.user
                    missing = [
                        perm for perm in requires_permissions if not user.has_perm(perm)
                    ]
                    if missing:
                        return cls(
                            ok=False,
                            result=None,
                            errors=[
                                {
                                    "field": None,
                                    "message": f"Permission refusée ({', '.join(missing)})",
                                }
                            ],
                        )

                # Wrap in transaction if atomic is True
                if atomic:
                    return cls._atomic_mutate(model, method_name, id, input)
                else:
                    return cls._non_atomic_mutate(model, method_name, id, input)

            @classmethod
            @transaction.atomic
            def _atomic_mutate(cls, model, method_name, id, input):
                return cls._execute_method(model, method_name, id, input)

            @classmethod
            def _non_atomic_mutate(cls, model, method_name, id, input):
                return cls._execute_method(model, method_name, id, input)

            @classmethod
            def _execute_method(cls, model, method_name, id, input):
                try:
                    instance = model.objects.get(pk=id)
                    method_func = getattr(instance, method_name)

                    if input:
                        result = method_func(**input)
                    else:
                        result = method_func()

                    if isinstance(result, models.Model):
                        result.save()

                    return cls(ok=True, result=result, errors=[])

                except model.DoesNotExist:
                    return cls(
                        ok=False,
                        result=None,
                        errors=[
                            {
                                "field": "id",
                                "message": f"{model.__name__} with id {id} does not exist",
                            }
                        ],
                    )
                except ValidationError as exc:
                    if atomic:
                        transaction.set_rollback(True)
                    return cls(
                        ok=False,
                        result=None,
                        errors=build_validation_errors(exc),
                    )
                except Exception as e:
                    if atomic:
                        transaction.set_rollback(True)
                    return cls(
                        ok=False,
                        result=None,
                        errors=[
                            {
                                "field": None,
                                "message": f"Failed to execute {method_name}: {str(e)}",
                            }
                        ],
                    )

        # Use custom name if provided
        mutation_name = custom_name or f"{model_name}{method_name.title()}"

        mutation_class = type(
            mutation_name,
            (MethodMutation,),
            {"__doc__": description or f"Execute {method_name} on {model_name}"},
        )

        # Add business logic metadata
        if is_business_logic:
            mutation_class._is_business_logic = True
            mutation_class._business_logic_category = getattr(
                method, "_business_logic_category", "general"
            )

        return mutation_class

    def generate_all_mutations(
        self, model: Type[models.Model]
    ) -> Dict[str, graphene.Field]:
        """
        Generates all mutations for a model, including CRUD operations and method mutations.
        """
        mutations = {}
        model_name = model.__name__.lower()
        # Generate CRUD mutations if enabled
        if self.settings.enable_create:
            mutation_class = self.generate_create_mutation(model)
            mutations[f"create_{model_name}"] = mutation_class.Field()

        if self.settings.enable_update:
            mutation_class = self.generate_update_mutation(model)
            mutations[f"update_{model_name}"] = mutation_class.Field()

        if self.settings.enable_delete:
            mutation_class = self.generate_delete_mutation(model)
            mutations[f"delete_{model_name}"] = mutation_class.Field()

        # Generate bulk mutations if enabled
        if self.settings.enable_bulk_operations:
            bulk_create_class = self.generate_bulk_create_mutation(model)
            mutations[f"bulk_create_{model_name}"] = bulk_create_class.Field()

            bulk_update_class = self.generate_bulk_update_mutation(model)
            mutations[f"bulk_update_{model_name}"] = bulk_update_class.Field()

            bulk_delete_class = self.generate_bulk_delete_mutation(model)
            mutations[f"bulk_delete_{model_name}"] = bulk_delete_class.Field()

        # Generate method mutations if enabled

        introspector = ModelIntrospector(model)
        for method_name, method_info in introspector.get_model_methods().items():
            if method_info.is_mutation and not method_info.is_private:
                mutation = self.generate_method_mutation(model, method_info)
                if mutation:
                    mutations[f"{model_name}_{method_name}"] = mutation.Field()
        return mutations
