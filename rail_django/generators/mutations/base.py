"""
Base classes and mixins for mutation generators.

This module provides shared base classes and mixins for tenant handling,
permission checking, and other common functionality.
"""

import logging
from typing import Any, Optional, Type

import graphene
from django.db import models

from ...core.meta import get_model_graphql_meta

logger = logging.getLogger(__name__)


class TenantMixin:
    """Mixin providing tenant-scoped operations."""

    schema_name: str = "default"

    def _apply_tenant_scope(
        self,
        queryset: models.QuerySet,
        info: Optional[graphene.ResolveInfo],
        model: Type[models.Model],
        operation: str = "list",
    ) -> models.QuerySet:
        """
        Apply tenant scope to queryset.

        Args:
            queryset: The base queryset to filter
            info: GraphQL resolve info containing context
            model: The Django model class
            operation: The operation type for scoping

        Returns:
            Tenant-scoped queryset
        """
        if info is None:
            return queryset

        try:
            from ...extensions.multitenancy import apply_tenant_queryset
            from graphql import GraphQLError

            return apply_tenant_queryset(
                queryset,
                info,
                model,
                schema_name=getattr(self, "schema_name", "default"),
                operation=operation,
            )
        except ImportError:
            logger.debug("Multitenancy extension not available")
            return queryset
        except GraphQLError:
            raise
        except Exception as e:
            logger.warning(f"Failed to apply tenant scope: {e}")
            return queryset

    def _enforce_tenant_access(
        self,
        instance: models.Model,
        info: Optional[graphene.ResolveInfo],
        model: Type[models.Model],
        operation: str = "retrieve",
    ) -> None:
        """
        Verify instance belongs to current tenant.

        Args:
            instance: The model instance to check
            info: GraphQL resolve info containing context
            model: The Django model class
            operation: The operation type for access check

        Raises:
            PermissionDenied: If tenant access is denied
        """
        if info is None:
            return

        try:
            from ...extensions.multitenancy import ensure_tenant_access

            ensure_tenant_access(
                instance,
                info,
                model,
                schema_name=getattr(self, "schema_name", "default"),
                operation=operation,
            )
        except ImportError:
            pass  # Multitenancy not enabled
        except Exception as e:
            logger.warning(f"Tenant access check failed: {e}")
            raise

    def _apply_tenant_input(
        self,
        input_data: dict,
        info: Optional[graphene.ResolveInfo],
        model: Type[models.Model],
        operation: str = "create",
    ) -> dict:
        """
        Apply tenant context to input data.

        Args:
            input_data: The mutation input data
            info: GraphQL resolve info containing context
            model: The Django model class
            operation: The operation type

        Returns:
            Input data with tenant context applied
        """
        if info is None:
            return input_data

        try:
            from ...extensions.multitenancy import apply_tenant_to_input

            return apply_tenant_to_input(
                input_data,
                info,
                model,
                schema_name=getattr(self, "schema_name", "default"),
                operation=operation,
            )
        except ImportError:
            return input_data
        except Exception as e:
            logger.warning(f"Failed to apply tenant input: {e}")
            return input_data

    def _get_tenant_queryset(
        self,
        model: Type[models.Model],
        info: Optional[graphene.ResolveInfo],
        operation: str = "list",
    ) -> models.QuerySet:
        """
        Get a tenant-scoped queryset for a model.

        Args:
            model: The Django model class
            info: GraphQL resolve info containing context
            operation: The operation type for scoping

        Returns:
            Tenant-scoped queryset
        """
        return self._apply_tenant_scope(
            model.objects.all(), info, model, operation=operation
        )


class PermissionMixin:
    """Mixin providing permission checking operations."""

    def _has_operation_guard(
        self,
        graphql_meta: Any,
        operation: str,
    ) -> bool:
        """
        Check if operation has a guard defined.

        Args:
            graphql_meta: The GraphQLMeta for the model
            operation: The operation to check

        Returns:
            True if a guard is defined for this operation
        """
        if not graphql_meta:
            return False

        guards = getattr(graphql_meta, "_operation_guards", None) or {}
        return operation in guards or "*" in guards

    def _build_model_permission_name(
        self,
        model: Type[models.Model],
        operation: str,
    ) -> str:
        """
        Build permission name for model operation.

        Args:
            model: The Django model class
            operation: The operation type

        Returns:
            Permission string in format 'app_label.operation_modelname'
        """
        app_label = model._meta.app_label
        model_name = model._meta.model_name

        operation_map = {
            "create": "add",
            "retrieve": "view",
            "update": "change",
            "delete": "delete",
            "list": "view",
        }

        # Normalize bulk operations
        normalized_op = operation
        if operation.startswith("bulk_"):
            normalized_op = operation[5:]  # Remove 'bulk_' prefix

        perm_op = operation_map.get(normalized_op, normalized_op)
        return f"{app_label}.{perm_op}_{model_name}"

    def _enforce_model_permission(
        self,
        info: graphene.ResolveInfo,
        model: Type[models.Model],
        operation: str,
        graphql_meta: Optional[Any] = None,
    ) -> None:
        """
        Enforce model-level permission for operation.

        Args:
            info: GraphQL resolve info containing context
            model: The Django model class
            operation: The operation type
            graphql_meta: Optional GraphQLMeta instance

        Raises:
            GraphQLError: If permission is denied
        """
        from graphql import GraphQLError

        if graphql_meta is None:
            graphql_meta = get_model_graphql_meta(model)

        # Check if operation has a guard (overrides permission)
        if self._has_operation_guard(graphql_meta, operation):
            return  # Guard will handle authorization

        # Normalize bulk operations for guard checking
        normalized = operation
        if operation.startswith("bulk_"):
            normalized = operation[5:]
            if self._has_operation_guard(graphql_meta, normalized):
                return

        # Check require_authentication
        if getattr(graphql_meta, "require_authentication", False):
            user = getattr(info.context, "user", None)
            if not user or not getattr(user, "is_authenticated", False):
                raise GraphQLError("Authentication required")

        # Get user from context
        user = getattr(getattr(info, "context", None), "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise GraphQLError("Authentication required")

        # Check model permission if enabled
        permission = self._build_model_permission_name(model, operation)

        if hasattr(user, "has_perm") and callable(user.has_perm):
            if not user.has_perm(permission):
                raise GraphQLError(f"Permission required: {permission}")


class MutationGeneratorBase(TenantMixin, PermissionMixin):
    """
    Base class for mutation generators with common functionality.

    Combines tenant and permission handling into a single base class
    that can be used by all mutation generators.
    """

    def __init__(self, schema_name: str = "default"):
        """
        Initialize the mutation generator base.

        Args:
            schema_name: Name of the schema for multi-schema support
        """
        self.schema_name = schema_name

    def _get_nested_handler(
        self,
        info: Optional[graphene.ResolveInfo] = None,
    ):
        """
        Get or create nested operation handler.

        Args:
            info: GraphQL resolve info containing context

        Returns:
            NestedOperationHandler instance
        """
        from .nested import NestedOperationHandler

        if info and hasattr(info.context, "mutation_generator"):
            handler = getattr(
                info.context.mutation_generator, "nested_handler", None
            )
            if handler:
                return handler

        return NestedOperationHandler(schema_name=self.schema_name)

    def _ensure_operation_access(
        self,
        model: Type[models.Model],
        operation: str,
        info: Optional[graphene.ResolveInfo],
        instance: Optional[models.Model] = None,
    ) -> None:
        """
        Ensure the user has access to perform the operation.

        Combines model permission checks with GraphQLMeta operation access.

        Args:
            model: The Django model class
            operation: The operation type
            info: GraphQL resolve info containing context
            instance: Optional instance for instance-level checks

        Raises:
            GraphQLError: If access is denied
        """
        if info is None:
            return

        graphql_meta = get_model_graphql_meta(model)
        self._enforce_model_permission(info, model, operation, graphql_meta)
        graphql_meta.ensure_operation_access(operation, info=info, instance=instance)
