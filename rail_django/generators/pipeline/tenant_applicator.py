"""
Tenant applicator wrapper for the pipeline.

Provides a consistent interface for tenant operations used by pipeline steps.
"""

from typing import Any, Optional

import graphene
from django.db import models


class TenantApplicator:
    """
    Wrapper for tenant-related operations.

    Provides methods for applying tenant scoping to querysets and
    injecting tenant fields into mutation input data.
    """

    def __init__(self, schema_name: str = "default"):
        """
        Initialize tenant applicator.

        Args:
            schema_name: Schema name for multi-schema support
        """
        self.schema_name = schema_name

    def apply_tenant_scope(
        self,
        queryset: models.QuerySet,
        info: graphene.ResolveInfo,
        model: type[models.Model],
        *,
        operation: str = "read",
    ) -> models.QuerySet:
        """
        Apply tenant scoping to a queryset.

        Args:
            queryset: Base queryset
            info: GraphQL resolve info
            model: Django model class
            operation: Operation type (read, update, delete)

        Returns:
            Scoped queryset
        """
        try:
            from ...extensions.multitenancy import apply_tenant_queryset
        except ImportError:
            return queryset

        return apply_tenant_queryset(
            queryset,
            info,
            model,
            schema_name=self.schema_name,
            operation=operation,
        )

    def apply_tenant_input(
        self,
        input_data: dict[str, Any],
        info: graphene.ResolveInfo,
        model: type[models.Model],
        *,
        operation: str = "create",
    ) -> dict[str, Any]:
        """
        Apply tenant fields to input data.

        Args:
            input_data: Original input data
            info: GraphQL resolve info
            model: Django model class
            operation: Operation type (create, update)

        Returns:
            Input data with tenant fields injected
        """
        try:
            from ...extensions.multitenancy import apply_tenant_to_input
        except ImportError:
            return input_data

        return apply_tenant_to_input(
            input_data,
            info,
            model,
            schema_name=self.schema_name,
            operation=operation,
        )

    def ensure_tenant_access(
        self,
        instance: models.Model,
        info: graphene.ResolveInfo,
        model: type[models.Model],
        *,
        operation: str = "read",
    ) -> None:
        """
        Ensure user has tenant access to an instance.

        Args:
            instance: Model instance to check
            info: GraphQL resolve info
            model: Django model class
            operation: Operation type

        Raises:
            GraphQLError: If tenant access is denied
        """
        try:
            from ...extensions.multitenancy import ensure_tenant_access
        except ImportError:
            return

        ensure_tenant_access(
            instance,
            info,
            model,
            schema_name=self.schema_name,
            operation=operation,
        )
