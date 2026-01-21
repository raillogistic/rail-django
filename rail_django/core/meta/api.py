"""
GraphQL Meta Public API Methods

This module provides a mixin class containing the public API methods
for GraphQLMeta, including custom resolver/filter application,
quick filtering, and access control enforcement.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from django.db import models
from django.db.models import Q
from graphql import GraphQLError

from .coercion import resolve_condition_callable
from .config import OperationGuardConfig
from .security_loader import load_security_components

logger = logging.getLogger(__name__)


class GraphQLMetaAPIMixin:
    """
    Mixin providing public API methods for GraphQLMeta.

    This mixin contains methods for:
    - Enforcing operation access guards
    - Describing operation guards
    - Field exposure checks
    - Custom resolver/filter retrieval and application
    - Quick filter application
    - Configuration accessors
    """

    # These attributes are expected to be set by the main GraphQLMeta class
    model_class: type[models.Model]
    _operation_guards: dict[str, OperationGuardConfig]
    _exclude_fields_set: set[str]
    _read_only_fields: set[str]
    _write_only_fields: set[str]
    _include_fields_set: Optional[set[str]]
    custom_resolvers: dict[str, Any]
    custom_filters: dict[str, Any]
    quick_filter_fields: list[str]
    filtering: Any
    ordering_config: Any

    def ensure_operation_access(
        self,
        operation: str,
        info: Any,
        *,
        instance: Optional[models.Model] = None,
    ) -> None:
        """
        Enforce the configured access guard for a given operation.

        Args:
            operation: The operation name (e.g., "create", "update", "delete")
            info: GraphQL resolve info
            instance: Optional model instance for instance-level checks

        Raises:
            GraphQLError when the current user is not allowed to perform the operation.
        """
        guard = self._operation_guards.get(operation) or self._operation_guards.get("*")
        if not guard:
            return

        security = load_security_components()
        role_mgr = security["role_manager"]

        context = getattr(info, "context", None)
        user = getattr(context, "user", None)

        if guard.allow_anonymous:
            return

        if guard.require_authentication and not (user and user.is_authenticated):
            raise GraphQLError(
                guard.deny_message
                or f"Authentication required to perform '{operation}' "
                f"on {self.model_class.__name__}"
            )

        criteria_results: list[bool] = []

        if guard.roles:
            try:
                user_roles = set(role_mgr.get_user_roles(user))
            except Exception:
                user_roles = set()
            criteria_results.append(bool(user_roles & set(guard.roles)))

        if guard.permissions:
            if user:
                criteria_results.append(
                    any(user.has_perm(perm) for perm in guard.permissions)
                )
            else:
                criteria_results.append(False)

        if guard.condition:
            condition_callable = resolve_condition_callable(
                guard.condition, self.model_class
            )
            if condition_callable:
                try:
                    allowed = condition_callable(
                        user=user,
                        operation=operation,
                        info=info,
                        instance=instance,
                        model=self.model_class,
                    )
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning(
                        "Error evaluating guard condition '%s' on %s: %s",
                        guard.name,
                        self.model_class.__name__,
                        exc,
                    )
                    allowed = False
                criteria_results.append(bool(allowed))

        if not criteria_results:
            return

        if guard.match.lower() == "all":
            allowed = all(criteria_results)
        else:
            allowed = any(criteria_results)

        if not allowed:
            raise GraphQLError(
                guard.deny_message
                or f"Operation '{operation}' is not permitted "
                f"on {self.model_class.__name__}"
            )

    def describe_operation_guard(
        self,
        operation: str,
        *,
        user: Optional[Any] = None,
        instance: Optional[models.Model] = None,
    ) -> dict[str, Any]:
        """
        Evaluate the configured access guard without raising.

        Args:
            operation: The operation name
            user: The user to check access for
            instance: Optional model instance for instance-level checks

        Returns:
            Dictionary with guarded, allowed, and reason keys
        """
        guard = self._operation_guards.get(operation) or self._operation_guards.get("*")
        if not guard:
            return {"guarded": False, "allowed": True, "reason": None}

        security = load_security_components()
        role_mgr = security["role_manager"]

        if guard.allow_anonymous:
            return {"guarded": True, "allowed": True, "reason": None}

        if guard.require_authentication and not (user and user.is_authenticated):
            return {
                "guarded": True,
                "allowed": False,
                "reason": guard.deny_message
                or "Authentification requise pour accéder à cette opération.",
            }

        criteria_results: list[bool] = []
        failure_reasons: list[str] = []

        if guard.roles:
            try:
                user_roles = set(role_mgr.get_user_roles(user))
            except Exception:
                user_roles = set()
            role_allowed = bool(user_roles & set(guard.roles))
            criteria_results.append(role_allowed)
            if not role_allowed:
                failure_reasons.append("Rôle requis manquant")

        if guard.permissions:
            permission_allowed = any(user.has_perm(perm) for perm in guard.permissions)
            criteria_results.append(permission_allowed)
            if not permission_allowed:
                failure_reasons.append("Permission manquante")

        if guard.condition:
            condition_callable = resolve_condition_callable(
                guard.condition, self.model_class
            )
            if condition_callable:
                try:
                    condition_allowed = bool(
                        condition_callable(
                            user=user,
                            operation=operation,
                            info=None,
                            instance=instance,
                            model=self.model_class,
                        )
                    )
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning(
                        "Error evaluating guard condition '%s' on %s: %s",
                        guard.name,
                        self.model_class.__name__,
                        exc,
                    )
                    condition_allowed = False
                criteria_results.append(condition_allowed)
                if not condition_allowed:
                    failure_reasons.append("Condition d'accès non satisfaite")

        if not criteria_results:
            return {"guarded": True, "allowed": True, "reason": None}

        match = guard.match.lower()
        allowed = all(criteria_results) if match == "all" else any(criteria_results)
        reason = None
        if not allowed:
            reason = guard.deny_message or "; ".join(failure_reasons) or "Accès refusé."
        return {"guarded": True, "allowed": allowed, "reason": reason}

    def should_expose_field(self, field_name: str, *, for_input: bool = False) -> bool:
        """
        Determine whether a field should be exposed based on field configuration.

        Args:
            field_name: Name of the field to check
            for_input: True when evaluating mutation/input exposure

        Returns:
            True if the field should be exposed, False otherwise
        """
        if field_name in self._exclude_fields_set:
            return False

        if for_input and field_name in self._read_only_fields:
            return False

        if not for_input and field_name in self._write_only_fields:
            return False

        if self._include_fields_set is not None:
            return field_name in self._include_fields_set

        return True

    def get_custom_resolver(self, resolver_name: str) -> Optional[Callable]:
        """
        Get a custom resolver by name.

        Args:
            resolver_name: Name of the resolver to retrieve

        Returns:
            The resolver function or None if not found
        """
        resolver = self.custom_resolvers.get(resolver_name)

        if isinstance(resolver, str):
            if hasattr(self.model_class, resolver):
                return getattr(self.model_class, resolver)
            logger.warning(
                "Custom resolver method '%s' not found on model %s",
                resolver,
                self.model_class.__name__,
            )
            return None

        return resolver

    def get_custom_filter(self, filter_name: str) -> Optional[Callable]:
        """
        Get a custom filter by name.

        Args:
            filter_name: Name of the filter to retrieve

        Returns:
            The filter function or None if not found
        """
        filter_func = self.custom_filters.get(filter_name)

        if isinstance(filter_func, str):
            if hasattr(self.model_class, filter_func):
                return getattr(self.model_class, filter_func)
            logger.warning(
                "Custom filter method '%s' not found on model %s",
                filter_func,
                self.model_class.__name__,
            )
            return None

        return filter_func

    def get_custom_filters(self) -> dict[str, Any]:
        """
        Get all custom filters as django-filter Filter instances.

        Returns:
            Dictionary mapping filter names to Filter instances
        """
        from django_filters import BooleanFilter, CharFilter, NumberFilter

        filter_instances: dict[str, Any] = {}

        for filter_name, filter_func in self.custom_filters.items():
            callable_fn = filter_func
            if isinstance(filter_func, str):
                callable_fn = getattr(self.model_class, filter_func, None)
                if callable_fn is None:
                    logger.warning(
                        "Custom filter method '%s' not found on model %s",
                        filter_func,
                        self.model_class.__name__,
                    )
                    continue

            if not callable(callable_fn):
                logger.warning(
                    "Custom filter '%s' is neither string nor callable", filter_name
                )
                continue

            lower_name = filter_name.lower()
            if lower_name.startswith(("has_", "is_")) or "bool" in lower_name:
                filter_instances[filter_name] = BooleanFilter(method=callable_fn)
            elif "count" in lower_name or "number" in lower_name:
                filter_instances[filter_name] = NumberFilter(method=callable_fn)
            else:
                filter_instances[filter_name] = CharFilter(method=callable_fn)

        return filter_instances

    def apply_custom_resolver(
        self, resolver_name: str, queryset: models.QuerySet, info: Any, **kwargs
    ) -> models.QuerySet:
        """
        Apply a custom resolver to a queryset.

        Args:
            resolver_name: Name of the resolver to apply
            queryset: The queryset to modify
            info: GraphQL resolve info
            **kwargs: Additional arguments

        Returns:
            Modified queryset
        """
        resolver = self.get_custom_resolver(resolver_name)

        if resolver:
            try:
                if callable(resolver):
                    return resolver(queryset, info, **kwargs)
                logger.warning("Custom resolver '%s' is not callable", resolver_name)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(
                    "Error applying custom resolver '%s': %s", resolver_name, exc
                )

        return queryset

    def apply_custom_filter(
        self, filter_name: str, queryset: models.QuerySet, value: Any
    ) -> models.QuerySet:
        """
        Apply a custom filter to a queryset.

        Args:
            filter_name: Name of the filter to apply
            queryset: The queryset to filter
            value: The filter value

        Returns:
            Filtered queryset
        """
        filter_func = self.get_custom_filter(filter_name)

        if filter_func:
            try:
                if callable(filter_func):
                    return filter_func(queryset, value)
                logger.warning("Custom filter '%s' is not callable", filter_name)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Error applying custom filter '%s': %s", filter_name, exc)

        return queryset

    def apply_quick_filter(
        self, queryset: models.QuerySet, search_value: str
    ) -> models.QuerySet:
        """
        Apply quick filter to search across configured fields.

        Args:
            queryset: The queryset to filter
            search_value: The search term

        Returns:
            Filtered queryset
        """
        quick_fields = self.quick_filter_fields

        if not quick_fields or not search_value:
            return queryset

        q_objects = Q()
        lookup = self.filtering.quick_lookup or "icontains"

        for field_path in quick_fields:
            try:
                filter_kwargs = {f"{field_path}__{lookup}": search_value}
                q_objects |= Q(**filter_kwargs)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "Error building quick filter for field '%s': %s", field_path, exc
                )

        if q_objects:
            return queryset.filter(q_objects)

        return queryset

    def get_filter_fields(self) -> dict[str, list[str]]:
        """
        Get the filter fields configuration.

        Returns:
            Dictionary mapping field names to allowed lookups
        """
        return {
            name: cfg.lookups[:] if cfg.lookups else []
            for name, cfg in self.filtering.fields.items()
        }

    def get_ordering_fields(self) -> list[str]:
        """
        Get the ordering fields configuration.

        Returns:
            List of allowed ordering field names
        """
        if self.ordering_config.allowed:
            return list(self.ordering_config.allowed)
        if self.ordering_config.default:
            return list(self.ordering_config.default)
        return []

    def has_custom_resolver(self, resolver_name: str) -> bool:
        """
        Check if a custom resolver exists.

        Args:
            resolver_name: Name of the resolver to check

        Returns:
            True if the resolver exists
        """
        return resolver_name in self.custom_resolvers

    def has_custom_filter(self, filter_name: str) -> bool:
        """
        Check if a custom filter exists.

        Args:
            filter_name: Name of the filter to check

        Returns:
            True if the filter exists
        """
        return filter_name in self.custom_filters

    def has_quick_filter(self) -> bool:
        """
        Check if quick filter is configured.

        Returns:
            True if quick filter fields are configured
        """
        return bool(self.quick_filter_fields)
