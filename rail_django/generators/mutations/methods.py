"""
Method-based mutation builders and audit helpers.
"""

from typing import Any, Dict, Optional, Type
import inspect

import graphene
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from graphene.types.unmountedtype import UnmountedType

from ...core.exceptions import GraphQLAutoError
from ...core.meta import get_model_graphql_meta
from ...core.mutation_permissions import (
    evaluate_mutation_access,
    get_mutation_access_config,
)
from ..introspector import MethodInfo
from ..pipeline.utils import decode_global_id
from .errors import (
    MutationError,
    build_graphql_auto_errors,
    build_integrity_errors,
    build_mutation_error,
    build_validation_errors,
)


def _wrap_with_audit(model: type[models.Model], operation: str, func):
    try:
        from ...security.audit_logging import audit_data_modification
    except Exception:
        return func
    return audit_data_modification(model, operation)(func)


def _infer_audit_operation(name: Optional[str]) -> str:
    if not name:
        return "update"
    lowered = name.lower()
    if lowered.startswith(("create", "add", "register", "signup", "import")):
        return "create"
    if lowered.startswith(("delete", "remove", "archive", "purge", "clear")):
        return "delete"
    if lowered.startswith(
        ("update", "set", "edit", "patch", "upsert", "enable", "disable")
    ):
        return "update"
    if "delete" in lowered or "remove" in lowered:
        return "delete"
    if "create" in lowered or "add" in lowered:
        return "create"
    return "update"


def _infer_guard_operation(
    name: Optional[str], action_kind: Optional[str] = None
) -> str:
    if action_kind == "confirm":
        return "update"
    return _infer_audit_operation(name)


def _validate_mutation_access(
    info: graphene.ResolveInfo,
    method: Any,
    *,
    instance: Any = None,
    input_data: Any = None,
    model: Any = None,
    root: Any = None,
) -> Optional[list[MutationError]]:
    access = get_mutation_access_config(method)
    if access is None:
        return None

    user = getattr(getattr(info, "context", None), "user", None)
    decision = evaluate_mutation_access(
        access,
        user=user,
        info=info,
        instance=instance,
        input_data=input_data,
        model=model,
        method=method,
        root=root,
    )
    if not decision.get("allowed", False):
        return [build_mutation_error(decision.get("reason") or "Permission denied")]
    return None


def _resolve_instance_from_id(
    queryset: models.QuerySet,
    model: type[models.Model],
    raw_id: Any,
):
    try:
        return queryset.get(pk=raw_id)
    except (ValueError, model.DoesNotExist):
        pass

    _, decoded_id = decode_global_id(str(raw_id))
    if decoded_id != str(raw_id):
        return queryset.get(pk=decoded_id)

    raise model.DoesNotExist


def _mount_result_field(output_type: Any):
    if isinstance(output_type, UnmountedType):
        return output_type

    if isinstance(output_type, type):
        if issubclass(output_type, graphene.ObjectType):
            return graphene.Field(output_type)
        if issubclass(output_type, UnmountedType):
            return output_type()

    return graphene.Field(output_type)


def _normalize_method_payload(payload: Any) -> Any:
    if payload is None:
        return None

    if isinstance(payload, dict):
        return dict(payload)

    meta = getattr(payload, "_meta", None)
    fields = getattr(meta, "fields", None)
    if fields:
        normalized: dict[str, Any] = {}
        for field_name in fields:
            field_value = getattr(payload, field_name, None)
            if field_value is not None:
                normalized[field_name] = field_value
        return normalized

    return payload


def convert_method_to_mutation(
    self,
    model: type[models.Model],
    method_name: str,
    custom_input_type: Optional[type[graphene.InputObjectType]] = None,
    custom_output_type: Optional[type[graphene.ObjectType]] = None,
) -> Optional[type[graphene.Mutation]]:
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
                param.annotation if param.annotation != inspect.Parameter.empty else Any
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

    graphql_meta = get_model_graphql_meta(model)
    guard_operation = _infer_guard_operation(method_name)

    uses_input_argument = custom_input_type is not None

    class ConvertedMethodMutation(graphene.Mutation):
        model_class = model

        class Arguments:
            id = graphene.ID(required=True)
            if uses_input_argument and input_type:
                input = input_type(required=True)

        # Standardized return format
        ok = graphene.Boolean()
        result = _mount_result_field(output_type)
        errors = graphene.List(MutationError)

        @classmethod
        @transaction.atomic
        def mutate(
            cls,
            root: Any,
            info: graphene.ResolveInfo,
            id: str,
            input: Any = None,
            **kwargs,
        ):
            try:
                scoped = self._apply_tenant_scope(
                    model.objects.all(),
                    info,
                    model,
                    operation=guard_operation,
                )
                instance = _resolve_instance_from_id(scoped, model, id)
                graphql_meta.ensure_operation_access(
                    guard_operation, info=info, instance=instance
                )
                permission_errors = _validate_mutation_access(
                    info,
                    method,
                    instance=instance,
                    input_data=kwargs,
                    model=model,
                    root=root,
                )
                if permission_errors:
                    return cls(
                        ok=False,
                        result=None,
                        errors=permission_errors,
                    )
                method_func = getattr(instance, method_name)

                if uses_input_argument:
                    filtered_kwargs = _normalize_method_payload(input)
                else:
                    method_params = set(signature.parameters.keys()) - {"self"}
                    filtered_kwargs = {
                        k: v for k, v in kwargs.items() if k in method_params
                    }
                if filtered_kwargs:
                    filtered_kwargs = self.input_validator.validate_and_sanitize(
                        model.__name__, filtered_kwargs
                    )

                def _perform_method(info, target, payload):
                    result = method_func(**payload)
                    if isinstance(result, models.Model):
                        result.full_clean()
                        result.save()
                    return result

                audit_operation = _infer_audit_operation(method_name)
                audited_method = _wrap_with_audit(
                    model, audit_operation, _perform_method
                )
                result = audited_method(info, instance, filtered_kwargs)

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
            except GraphQLAutoError as exc:
                transaction.set_rollback(True)
                return cls(
                    ok=False,
                    result=None,
                    errors=build_graphql_auto_errors(exc),
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

    if not uses_input_argument:
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


def generate_method_mutation(
    self, model: type[models.Model], method_info: MethodInfo
) -> Optional[type[graphene.Mutation]]:
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
    atomic = getattr(method, "_atomic", True)
    action_kind = getattr(method, "_action_kind", None)
    guard_operation = _infer_guard_operation(method_name, action_kind)
    graphql_meta = get_model_graphql_meta(model)

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
                param.annotation if param.annotation != inspect.Parameter.empty else Any
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
        model_class = model

        class Arguments:
            id = graphene.ID(required=True)
            if input_type:
                input = input_type(required=True)

        # Standardized return format
        ok = graphene.Boolean()
        result = _mount_result_field(output_type)
        errors = graphene.List(MutationError)

        @classmethod
        def mutate(
            cls,
            root: Any,
            info: graphene.ResolveInfo,
            id: str,
            input: dict[str, Any] = None,
        ):
            # Wrap in transaction if atomic is True
            if atomic:
                return cls._atomic_mutate(model, method_name, id, input, info)
            return cls._non_atomic_mutate(model, method_name, id, input, info)

        @classmethod
        @transaction.atomic
        def _atomic_mutate(cls, model, method_name, id, input, info):
            return cls._execute_method(model, method_name, id, input, info)

        @classmethod
        def _non_atomic_mutate(cls, model, method_name, id, input, info):
            return cls._execute_method(model, method_name, id, input, info)

        @classmethod
        def _execute_method(cls, model, method_name, id, input, info):
            try:
                scoped = self._apply_tenant_scope(
                    model.objects.all(),
                    info,
                    model,
                    operation=guard_operation,
                )
                instance = _resolve_instance_from_id(scoped, model, id)
                graphql_meta.ensure_operation_access(
                    guard_operation, info=info, instance=instance
                )
                permission_errors = _validate_mutation_access(
                    info,
                    method,
                    instance=instance,
                    input_data=input,
                    model=model,
                )
                if permission_errors:
                    return cls(
                        ok=False,
                        result=None,
                        errors=permission_errors,
                    )
                method_func = getattr(instance, method_name)

                def _perform_method(info, target, payload):
                    if payload:
                        result = method_func(**payload)
                    else:
                        result = method_func()
                    if isinstance(result, models.Model):
                        result.full_clean()
                        result.save()
                    return result

                audit_operation = _infer_audit_operation(method_name)
                audited_method = _wrap_with_audit(
                    model, audit_operation, _perform_method
                )
                validated_input = _normalize_method_payload(input)
                if validated_input:
                    validated_input = self.input_validator.validate_and_sanitize(
                        model.__name__, validated_input
                    )
                result = audited_method(info, instance, validated_input)

                return cls(ok=True, result=result, errors=[])

            except model.DoesNotExist:
                return cls(
                    ok=False,
                    result=None,
                    errors=[
                        build_mutation_error(
                            message=f"{model.__name__} with id {id} does not exist",
                            field="id",
                        )
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
            except IntegrityError as exc:
                if atomic:
                    transaction.set_rollback(True)
                return cls(
                    ok=False,
                    result=None,
                    errors=build_integrity_errors(model, exc),
                )
            except GraphQLAutoError as exc:
                if atomic:
                    transaction.set_rollback(True)
                return cls(
                    ok=False,
                    result=None,
                    errors=build_graphql_auto_errors(exc),
                )
            except Exception as e:
                if atomic:
                    transaction.set_rollback(True)
                return cls(
                    ok=False,
                    result=None,
                    errors=[
                        build_mutation_error(
                            message=f"Failed to execute {method_name}: {str(e)}"
                        )
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
