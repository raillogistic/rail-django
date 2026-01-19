"""
CRUD mutation builders.
"""

from typing import Any, Dict, List, Type

import graphene
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction

from ..core.meta import get_model_graphql_meta
from .introspector import ModelIntrospector
from ..core.exceptions import GraphQLAutoError
from .mutations_errors import (
    MutationError,
    build_error_list,
    build_graphql_auto_errors,
    build_integrity_errors,
    build_mutation_error,
    build_validation_errors,
)
from .mutations_limits import _get_nested_validation_limits, _validate_nested_limits
from .mutations_methods import _wrap_with_audit
from .nested_operations import NestedOperationHandler


def generate_create_mutation(
    self, model: type[models.Model]
) -> type[graphene.Mutation]:
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
    read_only_fields = set(
        getattr(graphql_meta.field_config, "read_only", []) or []
    )

    class CreateMutation(graphene.Mutation):
        model_class = model

        class Arguments:
            input = input_type(required=True)

        # Standardized return type
        ok = graphene.Boolean()
        object = graphene.Field(model_type)
        errors = graphene.List(MutationError)

        @classmethod
        @transaction.atomic
        def mutate(
            cls, root: Any, info: graphene.ResolveInfo, input: dict[str, Any]
        ) -> "CreateMutation":
            try:
                self._enforce_model_permission(info, model, "create", graphql_meta)
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

                # Auto-populate created_by if missing and available on model
                if "created_by" not in input:
                    try:
                        field = model._meta.get_field("created_by")
                        user = info.context.user if hasattr(info.context, "user") else None
                        if user and user.is_authenticated and field:
                            input["created_by"] = user.id
                    except Exception:
                        pass

                input = self._apply_tenant_input(
                    input, info, model, operation="create"
                )

                input = self.input_validator.validate_and_sanitize(
                    model.__name__, input
                )

                # Use the nested operation handler for advanced nested operations
                nested_handler = cls._get_nested_handler(info)

                limit_errors = _validate_nested_limits(
                    input, _get_nested_validation_limits(info, nested_handler)
                )
                if limit_errors:
                    return cls(ok=False, object=None, errors=limit_errors)

                # Validate nested data before processing
                validation_errors = nested_handler.validate_nested_data(
                    model, input, "create"
                )
                if validation_errors:
                    return cls(
                        ok=False,
                        object=None,
                        errors=build_error_list(validation_errors),
                    )

                # Handle nested create with comprehensive validation and transaction management
                def _perform_create(info, payload):
                    return nested_handler.handle_nested_create(
                        model, payload, info=info
                    )

                audited_create = _wrap_with_audit(model, "create", _perform_create)
                instance = audited_create(info, input)

                return cls(ok=True, object=instance, errors=None)

            except ValidationError as exc:
                error_objects = build_validation_errors(exc)
                return cls(ok=False, object=None, errors=error_objects)
            except GraphQLAutoError as exc:
                error_objects = build_graphql_auto_errors(exc)
                return cls(ok=False, object=None, errors=error_objects)
            except IntegrityError as exc:
                transaction.set_rollback(True)
                return cls(
                    ok=False,
                    object=None,
                    errors=build_integrity_errors(model, exc),
                )
            except Exception as exc:
                transaction.set_rollback(True)
                error_objects = [
                    build_mutation_error(
                        message=f"Failed to create {model_name}: {str(exc)}"
                    )
                ]
                return cls(ok=False, object=None, errors=error_objects)

        @classmethod
        def _sanitize_input_data(cls, input_data: dict[str, Any]) -> dict[str, Any]:
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
                if isinstance(value, dict):
                    return {k: sanitize_value(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [sanitize_value(item) for item in value]
                return value

            return {k: sanitize_value(v) for k, v in input_data.items()}

        @classmethod
        def _normalize_enum_inputs(
            cls, input_data: dict[str, Any], model: type[models.Model]
        ) -> dict[str, Any]:
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
            normalized: dict[str, Any] = input_data.copy()

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
            cls, input_data: dict[str, Any], model: type[models.Model]
        ) -> dict[str, Any]:
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
            introspector = ModelIntrospector.for_model(model)
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
        def _get_mandatory_fields(cls, model: type[models.Model]) -> list[str]:
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
    self, model: type[models.Model]
) -> type[graphene.Mutation]:
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
        model_class = model

        class Arguments:
            id = graphene.ID(required=True)
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
            id: str,
            input: dict[str, Any],
        ) -> "UpdateMutation":
            try:
                input = cls._sanitize_input_data(input)
                record_id = id or input.get("id")
                if not record_id:
                    return cls(
                        ok=False,
                        object=None,
                        errors=[
                            MutationError(
                                field="id",
                                message="L'identifiant est requis pour la mise Çÿ jour.",
                            )
                        ],
                    )

                # Remove id from the update payload to avoid attempting to overwrite PK
                update_data = {
                    key: value for key, value in input.items() if key != "id"
                }

                self._enforce_model_permission(info, model, "update", graphql_meta)

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

                update_data = self._apply_tenant_input(
                    update_data, info, model, operation="update"
                )

                update_data = self.input_validator.validate_and_sanitize(
                    model.__name__, update_data
                )

                # Decode GraphQL ID to database ID if needed
                try:
                    scoped = self._apply_tenant_scope(
                        model.objects.all(), info, model, operation="update"
                    )
                    instance = scoped.get(pk=record_id)
                except (ValueError, model.DoesNotExist):
                    # If that fails, try to decode as GraphQL global ID
                    from graphql_relay import from_global_id

                    try:
                        decoded_type, decoded_id = from_global_id(record_id)
                        scoped = self._apply_tenant_scope(
                            model.objects.all(), info, model, operation="update"
                        )
                        instance = scoped.get(pk=decoded_id)
                    except Exception:
                        # If all else fails, raise the original error
                        scoped = self._apply_tenant_scope(
                            model.objects.all(), info, model, operation="update"
                        )
                        instance = scoped.get(pk=record_id)

                graphql_meta.ensure_operation_access(
                    "update", info=info, instance=instance
                )

                # Use the nested operation handler for advanced nested operations
                nested_handler = cls._get_nested_handler(info)

                limit_errors = _validate_nested_limits(
                    update_data, _get_nested_validation_limits(info, nested_handler)
                )
                if limit_errors:
                    return cls(ok=False, object=None, errors=limit_errors)

                # Validate nested data before processing
                validation_errors = nested_handler.validate_nested_data(
                    model, update_data, "update"
                )
                if validation_errors:
                    return cls(
                        ok=False,
                        object=None,
                        errors=build_error_list(validation_errors),
                    )

                # Handle nested update with comprehensive validation and transaction management
                def _perform_update(info, target, payload):
                    return nested_handler.handle_nested_update(
                        model, payload, target, info=info
                    )

                audited_update = _wrap_with_audit(model, "update", _perform_update)
                instance = audited_update(info, instance, update_data)

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
            except GraphQLAutoError as exc:
                error_objects = build_graphql_auto_errors(exc)
                return UpdateMutation(ok=False, object=None, errors=error_objects)
            except IntegrityError as exc:
                transaction.set_rollback(True)
                return UpdateMutation(
                    ok=False,
                    object=None,
                    errors=build_integrity_errors(model, exc),
                )
            except Exception as exc:
                transaction.set_rollback(True)
                error_objects = [
                    build_mutation_error(
                        message=f"Failed to update {model_name}: {str(exc)}"
                    )
                ]
                return UpdateMutation(ok=False, object=None, errors=error_objects)

        @classmethod
        def _sanitize_input_data(cls, input_data: dict[str, Any]) -> dict[str, Any]:
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
                if isinstance(value, dict):
                    return {k: sanitize_value(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [sanitize_value(item) for item in value]
                return value

            return {k: sanitize_value(v) for k, v in input_data.items()}

        @classmethod
        def _normalize_enum_inputs(
            cls, input_data: dict[str, Any], model: type[models.Model]
        ) -> dict[str, Any]:
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
            normalized: dict[str, Any] = input_data.copy()

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
            cls, input_data: dict[str, Any], model: type[models.Model]
        ) -> dict[str, Any]:
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
            introspector = ModelIntrospector.for_model(model)
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
        def _get_mandatory_fields(cls, model: type[models.Model]) -> list[str]:
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
    self, model: type[models.Model]
) -> type[graphene.Mutation]:
    """
    Generates a mutation for deleting a model instance.
    Supports cascade delete configuration.
    """
    model_type = self.type_generator.generate_object_type(model)
    model_name = model.__name__
    graphql_meta = get_model_graphql_meta(model)

    class DeleteMutation(graphene.Mutation):
        model_class = model

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
                self._enforce_model_permission(info, model, "delete", graphql_meta)
                scoped = self._apply_tenant_scope(
                    model.objects.all(), info, model, operation="delete"
                )
                instance = scoped.get(pk=id)
                graphql_meta.ensure_operation_access(
                    "delete", info=info, instance=instance
                )

                def _perform_delete(info, target):
                    target_pk = target.pk
                    target.delete()
                    try:
                        target.pk = target_pk
                    except Exception:
                        pass
                    return target

                audited_delete = _wrap_with_audit(model, "delete", _perform_delete)
                deleted_instance = audited_delete(info, instance)
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
