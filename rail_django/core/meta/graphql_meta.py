"""
GraphQL Meta Configuration System

This module provides the GraphQLMeta class for configuring GraphQL behavior
for Django models. The configuration is grouped by functional areas such as
filtering, field exposure, ordering, and custom resolvers so that model authors
can describe their API surface declaratively from a single place.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.core.exceptions import FieldDoesNotExist
from django.db import models

from .api import GraphQLMetaAPIMixin
from .builders import (
    build_access_control_config,
    build_classification_config,
    build_field_config,
    build_filtering_config,
    build_ordering_config,
    build_pipeline_config,
    build_resolver_config,
)
from .coercion import (
    coerce_access_level,
    coerce_operation_guard,
    coerce_visibility,
    convert_role_type,
    resolve_condition_callable,
)
from .config import (
    AccessControlConfig,
    ClassificationConfig,
    FieldExposureConfig,
    FieldGuardConfig,
    FilterFieldConfig,
    FilteringConfig,
    OperationGuardConfig,
    OrderingConfig,
    PipelineConfig,
    ResolverConfig,
    RoleConfig,
    RelationOperationConfig,
    FieldRelationConfig,
)
from .security_loader import load_security_components

logger = logging.getLogger(__name__)


class GraphQLMeta(GraphQLMetaAPIMixin):
    """
    Meta helper for configuring GraphQL behavior on Django models.

    Models can declare an inner ``GraphqlMeta`` (or ``GraphQLMeta``) class and
    describe their configuration using grouped sections:

        class MyModel(models.Model):
            ...

            class GraphqlMeta(GraphQLMeta):
                filtering = GraphQLMeta.Filtering(
                    quick=["name", "email"],
                    fields={
                        "name": GraphQLMeta.FilterField(lookups=["icontains", "eq"]),
                        "status": GraphQLMeta.FilterField(lookups=["eq", "in"]),
                    },
                )
                fields = GraphQLMeta.Fields(
                    include=["id", "name", "email", "status"],
                    read_only=["status"],
                )
                ordering = GraphQLMeta.Ordering(
                    allowed=["name", "created_at"],
                    default=["-created_at"],
                )
                resolvers = GraphQLMeta.Resolvers(
                    queries={"list": "resolve_custom_list"}
                )
    """

    # Class-level aliases for configuration classes
    FilterField = FilterFieldConfig
    Filtering = FilteringConfig
    Fields = FieldExposureConfig
    Ordering = OrderingConfig
    Resolvers = ResolverConfig
    Role = RoleConfig
    FieldGuard = FieldGuardConfig
    OperationGuard = OperationGuardConfig
    AccessControl = AccessControlConfig
    Classification = ClassificationConfig
    Pipeline = PipelineConfig
    RelationOperation = RelationOperationConfig
    FieldRelation = FieldRelationConfig

    def __init__(self, model_class: type[models.Model]):
        """
        Initialize GraphQLMeta configuration for a model.

        Args:
            model_class: The Django model class this meta is attached to.
        """
        self.model_class = model_class
        self.model_label = getattr(
            model_class._meta, "label_lower", model_class.__name__.lower()
        )
        self._meta_config = self._resolve_meta_class(model_class)
        self.tenant_field = (
            getattr(self._meta_config, "tenant_field", None)
            if self._meta_config is not None
            else None
        )

        # Build configurations using builder functions
        self.filtering: FilteringConfig = build_filtering_config(self._meta_config)
        self.field_config: FieldExposureConfig = build_field_config(self._meta_config)
        self.ordering_config: OrderingConfig = build_ordering_config(
            self._meta_config, model_class
        )
        self.resolvers: ResolverConfig = build_resolver_config(self._meta_config)
        self.access_config: AccessControlConfig = build_access_control_config(
            self._meta_config
        )
        self.classification_config: ClassificationConfig = build_classification_config(
            self._meta_config
        )
        self.pipeline_config: PipelineConfig = build_pipeline_config(self._meta_config)

        self.relations_config: dict[str, FieldRelationConfig] = getattr(
            self._meta_config, "relations", {}
        )
        # Optional custom metadata/hooks used by frontend schema consumers.
        self.custom_metadata = getattr(self._meta_config, "custom_metadata", None)
        self.field_metadata = getattr(self._meta_config, "field_metadata", None) or {}
        self.field_groups = getattr(self._meta_config, "field_groups", None)

        # Backwards-compatible attribute aliases
        self.custom_filters = self.filtering.custom
        self.filter_presets = self.filtering.presets
        self.computed_filters = getattr(self._meta_config, "computed_filters", {})
        self.custom_resolvers = self.resolvers.queries
        self.quick_filter_fields = list(self.filtering.quick)
        self.filters = {"quick": self.quick_filter_fields}
        self.filter_fields = {
            name: cfg.lookups[:] for name, cfg in self.filtering.fields.items()
        }
        self.ordering = list(
            self.ordering_config.allowed or self.ordering_config.default
        )
        self.include_fields = (
            list(self.field_config.include) if self.field_config.include else None
        )
        self.exclude_fields = list(self.field_config.exclude)

        # Internal sets for quick membership checks
        self._include_fields_set = (
            set(self.field_config.include) if self.field_config.include else None
        )
        self._exclude_fields_set = set(self.field_config.exclude)
        self._read_only_fields = set(self.field_config.read_only)
        self._write_only_fields = set(self.field_config.write_only)
        self._operation_guards = self._index_operation_guards()

        self._register_roles()
        self._register_field_permissions()
        self._register_classifications()

        self._validate_configuration()

    def get_relation_config(self, field_name: str) -> Optional[FieldRelationConfig]:
        """Get configuration for a specific relation field."""
        return self.relations_config.get(field_name)

    def is_operation_allowed(self, field_name: str, operation: str) -> bool:
        """Check if a specific operation (connect/create/etc) is allowed for a field."""
        config = self.get_relation_config(field_name)
        if not config:
            return True
        style = getattr(config, "style", "unified")
        if str(style).lower() == "id_only" and operation in {"create", "update"}:
            return False
        
        op_config = getattr(config, operation, None)
        if op_config and hasattr(op_config, "enabled"):
            return op_config.enabled
        return True

    def _resolve_meta_class(self, model_class: type[models.Model]) -> Any:
        """Return the declared GraphQL meta configuration class if it exists."""
        meta_decl = getattr(model_class, "GraphQLMeta", None) or getattr(
            model_class, "GraphqlMeta", None
        )
        if meta_decl is not None:
            return meta_decl
        try:
            from ..meta_json import get_model_meta_config

            return get_model_meta_config(model_class)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Could not load JSON GraphQLMeta for %s: %s",
                model_class.__name__,
                exc,
            )
            return None

    def _index_operation_guards(self) -> dict[str, OperationGuardConfig]:
        guards: dict[str, OperationGuardConfig] = {}
        for name, guard in self.access_config.operations.items():
            guards[name] = (
                guard
                if isinstance(guard, OperationGuardConfig)
                else coerce_operation_guard(name, guard)
            )
        return guards

    def _register_roles(self) -> None:
        components = load_security_components()
        RoleDefinition = components["RoleDefinition"]
        role_mgr = components["role_manager"]
        RoleTypeCls = components["RoleType"]
        for role in self.access_config.roles.values():
            try:
                role_definition = RoleDefinition(
                    name=role.name,
                    description=role.description,
                    role_type=convert_role_type(role.role_type, RoleTypeCls),
                    permissions=role.permissions,
                    parent_roles=role.parent_roles or None,
                    is_system_role=role.is_system_role,
                    max_users=role.max_users,
                )
                role_mgr.register_role(role_definition)
            except Exception as exc:
                logger.warning(
                    "Could not register GraphQLMeta role '%s' for %s: %s",
                    role.name,
                    self.model_class.__name__,
                    exc,
                )

    def _register_field_permissions(self) -> None:
        components = load_security_components()
        FieldPermissionRule = components["FieldPermissionRule"]
        field_permission_mgr = components["field_permission_manager"]
        for guard in self.access_config.fields:
            if not guard.field:
                continue
            access_level = coerce_access_level(guard.access, components)
            visibility = coerce_visibility(guard.visibility, components)
            condition = resolve_condition_callable(guard.condition, self.model_class)
            rule = FieldPermissionRule(
                field_name=guard.field,
                model_name=self.model_label,
                access_level=access_level,
                visibility=visibility,
                condition=condition,
                mask_value=guard.mask_value,
                roles=guard.roles or None,
                permissions=guard.permissions or None,
            )
            try:
                field_permission_mgr.register_field_rule(rule)
            except Exception as exc:
                logger.warning(
                    "Could not register field guard for %s.%s: %s",
                    self.model_class.__name__,
                    guard.field,
                    exc,
                )

    def _register_classifications(self) -> None:
        if not (
            self.classification_config.model or self.classification_config.fields
        ):
            return
        components = load_security_components()
        field_permission_mgr = components["field_permission_manager"]
        try:
            field_permission_mgr.register_classification_tags(
                self.model_class,
                model_tags=self.classification_config.model,
                field_tags=self.classification_config.fields,
            )
        except Exception as exc:
            logger.warning(
                "Could not register classification tags for %s: %s",
                self.model_class.__name__,
                exc,
            )

    def _validate_configuration(self) -> None:
        """Validate quick filter paths and ensure referenced fields exist."""
        for field_path in self.quick_filter_fields:
            self._validate_field_path(field_path)

        for field_name in self.filtering.fields.keys():
            self._validate_field_path(field_name)

    def _validate_field_path(self, field_path: str) -> None:
        """Validate that a field path exists on the model."""
        if not field_path:
            return

        try:
            current_model = self.model_class
            field_parts = field_path.split("__")

            for i, field_name in enumerate(field_parts):
                try:
                    field = current_model._meta.get_field(field_name)

                    if i < len(field_parts) - 1:
                        if hasattr(field, "related_model"):
                            current_model = field.related_model
                        else:
                            raise ValueError(
                                f"Field '{field_name}' in path '{field_path}' "
                                f"is not a relation"
                            )
                except FieldDoesNotExist as exc:
                    raise ValueError(
                        f"Field '{field_name}' does not exist on model "
                        f"{current_model.__name__}"
                    ) from exc

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Could not validate field path '%s' on model %s: %s",
                field_path,
                self.model_class.__name__,
                exc,
            )


def get_model_graphql_meta(model_class: type[models.Model]) -> GraphQLMeta:
    """
    Get or create GraphQLMeta configuration for a model.

    Args:
        model_class: The Django model class

    Returns:
        GraphQLMeta instance for the model
    """
    if not hasattr(model_class, "_graphql_meta_instance"):
        model_class._graphql_meta_instance = GraphQLMeta(model_class)

    return model_class._graphql_meta_instance
