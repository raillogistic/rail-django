"""
Bulk mutation builders.
"""

from typing import Any, Dict, List, Type

import graphene
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction

from ..core.meta import get_model_graphql_meta
from .mutations_errors import (
    MutationError,
    build_integrity_errors,
    build_mutation_error,
    build_validation_errors,
)
from .mutations_methods import _wrap_with_audit


def generate_bulk_create_mutation(
    self, model: type[models.Model]
) -> type[graphene.Mutation]:
    """
    Generates a mutation for creating multiple model instances in bulk.
    """
    model_type = self.type_generator.generate_object_type(model)
    input_type = self.type_generator.generate_input_type(
        model, mutation_type="create"
    )
    model_name = model.__name__
    graphql_meta = get_model_graphql_meta(model)

    class BulkCreateMutation(graphene.Mutation):
        model_class = model

        class Arguments:
            inputs = graphene.List(input_type, required=True)

        # Standardized return type
        ok = graphene.Boolean()
        objects = graphene.List(model_type)  # Using 'objects' for multiple items
        errors = graphene.List(MutationError)

        @classmethod
        @transaction.atomic
        def mutate(
            cls, root: Any, info: graphene.ResolveInfo, inputs: list[dict[str, Any]]
        ) -> "BulkCreateMutation":
            try:
                graphql_meta.ensure_operation_access("bulk_create", info=info)

                def _perform_create(info, payload):
                    return model.objects.create(**payload)

                audited_create = _wrap_with_audit(model, "create", _perform_create)
                instances = []
                for input_data in inputs:
                    # Normalize enum inputs (GraphQL Enum -> underlying Django values)
                    input_data = cls._normalize_enum_inputs(input_data, model)
                    instance = audited_create(info, input_data)
                    instances.append(instance)

                return cls(ok=True, objects=instances, errors=[])

            except ValidationError as e:
                return cls(
                    ok=False,
                    objects=[],
                    errors=build_validation_errors(e),
                )
            except IntegrityError as e:
                transaction.set_rollback(True)
                return cls(
                    ok=False,
                    objects=[],
                    errors=build_integrity_errors(model, e),
                )
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
            cls, input_data: dict[str, Any], model: type[models.Model]
        ) -> dict[str, Any]:
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
            normalized: dict[str, Any] = input_data.copy()

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
    self, model: type[models.Model]
) -> type[graphene.Mutation]:
    """
    Generates a mutation for updating multiple model instances in bulk.
    """
    model_type = self.type_generator.generate_object_type(model)
    input_type = self.type_generator.generate_input_type(
        model, partial=True, mutation_type="update"
    )
    model_name = model.__name__
    graphql_meta = get_model_graphql_meta(model)

    class BulkUpdateInput(graphene.InputObjectType):
        id = graphene.ID(required=True)
        data = input_type(required=True)

    class BulkUpdateMutation(graphene.Mutation):
        model_class = model

        class Arguments:
            inputs = graphene.List(BulkUpdateInput, required=True)

        # Standardized return type
        ok = graphene.Boolean()
        objects = graphene.List(model_type)  # Using 'objects' for multiple items
        errors = graphene.List(MutationError)

        @classmethod
        @transaction.atomic
        def mutate(
            cls, root: Any, info: graphene.ResolveInfo, inputs: list[dict[str, Any]]
        ) -> "BulkUpdateMutation":
            try:
                graphql_meta.ensure_operation_access("bulk_update", info=info)

                def _perform_update(info, target, payload):
                    for field, value in payload.items():
                        setattr(target, field, value)
                    target.full_clean()
                    target.save()
                    return target

                audited_update = _wrap_with_audit(model, "update", _perform_update)
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
                    instance = audited_update(info, instance, update_data)
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
                return cls(
                    ok=False,
                    objects=[],
                    errors=build_integrity_errors(model, exc),
                )
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

        @classmethod
        def _normalize_enum_inputs(
            cls, input_data: dict[str, Any], model: type[models.Model]
        ) -> dict[str, Any]:
            normalized: dict[str, Any] = input_data.copy()

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
        f"BulkUpdate{model_name}",
        (BulkUpdateMutation,),
        {"__doc__": f"Update multiple {model_name} instances"},
    )


def generate_bulk_delete_mutation(
    self, model: type[models.Model]
) -> type[graphene.Mutation]:
    """
    Generates a mutation for deleting multiple model instances in bulk.
    """
    model_type = self.type_generator.generate_object_type(model)
    model_name = model.__name__
    graphql_meta = get_model_graphql_meta(model)

    class BulkDeleteMutation(graphene.Mutation):
        model_class = model

        class Arguments:
            ids = graphene.List(graphene.ID, required=True)

        # Standardized return type
        ok = graphene.Boolean()
        objects = graphene.List(model_type)  # Return deleted objects
        errors = graphene.List(MutationError)

        @classmethod
        @transaction.atomic
        def mutate(
            cls, root: Any, info: graphene.ResolveInfo, ids: list[str]
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

                def _perform_delete(info, target):
                    target.delete()
                    return target

                audited_delete = _wrap_with_audit(model, "delete", _perform_delete)
                for inst in deleted_instances:
                    audited_delete(info, inst)
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
