"""
Mutation Generation System for Django GraphQL Auto-Generation

This module provides the MutationGenerator class, which is responsible for creating
GraphQL mutations for Django models, including CRUD operations and custom method mutations.

The generator uses a pipeline-based architecture for improved testability and customization.
"""

from typing import Any, Optional, Union, get_origin

import graphene
from django.db import models
from graphene.types.generic import GenericScalar
from graphql import GraphQLError

from ..introspector import MethodInfo, ModelIntrospector
from .bulk import (
    generate_bulk_create_mutation as _generate_bulk_create_mutation,
    generate_bulk_delete_mutation as _generate_bulk_delete_mutation,
    generate_bulk_update_mutation as _generate_bulk_update_mutation,
)
from .errors import (  # noqa: F401
    MutationError,
    build_error_list,
    build_integrity_errors,
    build_mutation_error,
    build_validation_errors,
)
from .methods import (
    convert_method_to_mutation as _convert_method_to_mutation,
    generate_method_mutation as _generate_method_mutation,
)
from ..nested import NestedOperationHandler
from ..types import TypeGenerator
from ...core.error_handling import get_error_handler
from ...core.meta import get_model_graphql_meta
from ...core.security import get_auth_manager, get_authz_manager, get_input_validator
from ...core.services import get_query_optimizer
from ...core.settings import MutationGeneratorSettings


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

    The generator uses a pipeline-based architecture for improved testability
    and customization.
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
        self._mutation_classes: dict[str, type[graphene.Mutation]] = {}
        self.nested_handler = NestedOperationHandler(
            self.settings, schema_name=self.schema_name
        )

        # Initialize pipeline components
        self._init_pipeline_backend()

    def _has_operation_guard(self, graphql_meta, operation: str) -> bool:
        guards = getattr(graphql_meta, "_operation_guards", None) or {}
        return operation in guards or "*" in guards

    def _build_model_permission_name(
        self, model: type[models.Model], codename: str
    ) -> str:
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        return f"{app_label}.{codename}_{model_name}"

    def _normalize_permission_operation(self, operation: str) -> str:
        normalized = str(operation or "").strip().lower()
        if normalized.startswith("bulk_"):
            normalized = normalized[len("bulk_") :]
        return normalized

    def _get_permission_codename(self, operation: str) -> Optional[str]:
        normalized = self._normalize_permission_operation(operation)
        mapping = getattr(self.settings, "model_permission_codenames", None)
        codename = None
        if isinstance(mapping, dict):
            codename = mapping.get(operation) or mapping.get(normalized)
        if codename is None:
            return None
        codename = str(codename or "").strip()
        return codename or None

    def _enforce_model_permission(
        self,
        info: graphene.ResolveInfo,
        model: type[models.Model],
        operation: str,
        graphql_meta=None,
    ) -> None:
        if not getattr(
            self.authorization_manager.settings, "enable_authorization", True
        ):
            return
        if not getattr(self.settings, "require_model_permissions", True):
            return

        normalized = self._normalize_permission_operation(operation)
        if graphql_meta is not None:
            if self._has_operation_guard(graphql_meta, operation):
                return
            if normalized and self._has_operation_guard(graphql_meta, normalized):
                return

        user = getattr(getattr(info, "context", None), "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise GraphQLError("Authentication required")

        codename = self._get_permission_codename(operation)
        if not codename:
            return

        permission_name = self._build_model_permission_name(model, codename)
        has_perm = getattr(user, "has_perm", None)
        if not callable(has_perm) or not has_perm(permission_name):
            raise GraphQLError(f"Permission required: {permission_name}")

    def _apply_tenant_scope(
        self,
        queryset: models.QuerySet,
        info: graphene.ResolveInfo,
        model: type[models.Model],
        *,
        operation: str = "read",
    ) -> models.QuerySet:
        try:
            from ...extensions.multitenancy import apply_tenant_queryset
        except Exception:
            return queryset
        
        try:
            return apply_tenant_queryset(
                queryset,
                info,
                model,
                schema_name=self.schema_name,
                operation=operation,
            )
        except GraphQLError:
            raise
        except Exception:
            return queryset

    def _enforce_tenant_access(
        self,
        instance: models.Model,
        info: graphene.ResolveInfo,
        model: type[models.Model],
        *,
        operation: str = "read",
    ) -> None:
        try:
            from ...extensions.multitenancy import ensure_tenant_access
        except Exception:
            return
        ensure_tenant_access(
            instance, info, model, schema_name=self.schema_name, operation=operation
        )

    def _apply_tenant_input(
        self,
        input_data: dict[str, Any],
        info: graphene.ResolveInfo,
        model: type[models.Model],
        *,
        operation: str = "create",
    ) -> dict[str, Any]:
        try:
            from ...extensions.multitenancy import apply_tenant_to_input
        except Exception:
            return input_data
        return apply_tenant_to_input(
            input_data,
            info,
            model,
            schema_name=self.schema_name,
            operation=operation,
        )

    def _init_pipeline_backend(self) -> None:
        """Initialize pipeline backend components."""
        from ..pipeline import PipelineBuilder
        from ..pipeline.tenant_applicator import TenantApplicator

        self._pipeline_builder = PipelineBuilder(self.settings)
        self._tenant_applicator = TenantApplicator(self.schema_name)

        # Configure builder based on settings
        if not getattr(self.authorization_manager.settings, "enable_authorization", True):
            self._pipeline_builder.require_model_permissions(False)
        if not getattr(self.settings, "require_model_permissions", True):
            self._pipeline_builder.require_model_permissions(False)

    def generate_create_mutation(self, model: type[models.Model]) -> type[graphene.Mutation]:
        """
        Generate a create mutation for a model using the pipeline backend.
        """
        from ..pipeline.factories import create_mutation_factory

        model_type = self.type_generator.generate_object_type(model)
        input_type = self.type_generator.generate_input_type(model, mutation_type="create")
        graphql_meta = get_model_graphql_meta(model)

        return create_mutation_factory(
            model=model,
            model_type=model_type,
            input_type=input_type,
            graphql_meta=graphql_meta,
            pipeline_builder=self._pipeline_builder,
            nested_handler=self.nested_handler,
            input_validator=self.input_validator,
            tenant_applicator=self._tenant_applicator,
        )

    def generate_update_mutation(self, model: type[models.Model]) -> type[graphene.Mutation]:
        """
        Generate an update mutation for a model using the pipeline backend.
        """
        from ..pipeline.factories import update_mutation_factory

        model_type = self.type_generator.generate_object_type(model)
        input_type = self.type_generator.generate_input_type(
            model, partial=True, mutation_type="update"
        )
        graphql_meta = get_model_graphql_meta(model)

        return update_mutation_factory(
            model=model,
            model_type=model_type,
            input_type=input_type,
            graphql_meta=graphql_meta,
            pipeline_builder=self._pipeline_builder,
            nested_handler=self.nested_handler,
            input_validator=self.input_validator,
            tenant_applicator=self._tenant_applicator,
        )

    def generate_delete_mutation(self, model: type[models.Model]) -> type[graphene.Mutation]:
        """
        Generate a delete mutation for a model using the pipeline backend.
        """
        from ..pipeline.factories import delete_mutation_factory

        model_type = self.type_generator.generate_object_type(model)
        graphql_meta = get_model_graphql_meta(model)

        return delete_mutation_factory(
            model=model,
            model_type=model_type,
            graphql_meta=graphql_meta,
            pipeline_builder=self._pipeline_builder,
            tenant_applicator=self._tenant_applicator,
        )

    def generate_bulk_create_mutation(self, model: type[models.Model]) -> type[graphene.Mutation]:
        return _generate_bulk_create_mutation(self, model)

    def generate_bulk_update_mutation(self, model: type[models.Model]) -> type[graphene.Mutation]:
        return _generate_bulk_update_mutation(self, model)

    def generate_bulk_delete_mutation(self, model: type[models.Model]) -> type[graphene.Mutation]:
        return _generate_bulk_delete_mutation(self, model)

    def convert_method_to_mutation(
        self,
        model: type[models.Model],
        method_name: str,
        custom_input_type: Optional[type[graphene.InputObjectType]] = None,
        custom_output_type: Optional[type[graphene.ObjectType]] = None,
    ) -> Optional[type[graphene.Mutation]]:
        return _convert_method_to_mutation(
            self,
            model,
            method_name,
            custom_input_type=custom_input_type,
            custom_output_type=custom_output_type,
        )

    def _convert_python_type_to_graphql(
        self, python_type: Any
    ) -> type[graphene.Scalar]:
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
        self, model: type[models.Model], method_info: MethodInfo
    ) -> Optional[type[graphene.Mutation]]:
        return _generate_method_mutation(self, model, method_info)

    def generate_all_mutations(
        self, model: type[models.Model]
    ) -> dict[str, graphene.Field]:
        """
        Generates all mutations for a model, including CRUD operations and method mutations.
        """
        from graphene.utils.str_converters import to_camel_case, to_snake_case
        mutations = {}
        model_class_name = model.__name__
        # Generate CRUD mutations if enabled
        if self.settings.enable_create:
            mutation_class = self.generate_create_mutation(model)
            mutations[f"create{model_class_name}"] = mutation_class.Field()

        if self.settings.enable_update:
            mutation_class = self.generate_update_mutation(model)
            mutations[f"update{model_class_name}"] = mutation_class.Field()

        if self.settings.enable_delete:
            mutation_class = self.generate_delete_mutation(model)
            mutations[f"delete{model_class_name}"] = mutation_class.Field()

        # Generate bulk mutations if enabled
        if self.settings.enable_bulk_operations:
            should_generate = False

            # Check exclusion first
            if model_class_name in self.settings.bulk_exclude_models:
                should_generate = False
            # Check inclusion
            elif model_class_name in self.settings.bulk_include_models:
                should_generate = True
            # Check global auto-discovery
            elif self.settings.generate_bulk:
                should_generate = True

            if should_generate:
                bulk_create_class = self.generate_bulk_create_mutation(model)
                mutations[f"bulkCreate{model_class_name}"] = bulk_create_class.Field()

                bulk_update_class = self.generate_bulk_update_mutation(model)
                mutations[f"bulkUpdate{model_class_name}"] = bulk_update_class.Field()

                bulk_delete_class = self.generate_bulk_delete_mutation(model)
                mutations[f"bulkDelete{model_class_name}"] = bulk_delete_class.Field()

        # Generate method mutations if enabled

        introspector = ModelIntrospector.for_model(model)
        for method_name, method_info in introspector.get_model_methods().items():
            if method_info.is_mutation and not method_info.is_private:
                mutation = self.generate_method_mutation(model, method_info)
                if mutation:
                    method_token = to_camel_case(to_snake_case(method_name))
                    mutations[f"{method_token}{model_class_name}"] = mutation.Field()
        return mutations
