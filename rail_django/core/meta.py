"""
GraphQL Meta Configuration System

This module provides the GraphQLMeta class for configuring GraphQL behavior
for Django models. The configuration is grouped by functional areas such as
filtering, field exposure, ordering, and custom resolvers so that model authors
can describe their API surface declaratively from a single place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Type, Union

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Q
from graphql import GraphQLError

logger = logging.getLogger(__name__)

_SECURITY_COMPONENTS: Optional[dict[str, Any]] = None


def _load_security_components() -> dict[str, Any]:
    global _SECURITY_COMPONENTS
    if _SECURITY_COMPONENTS is None:
        from rail_django.security import (
            FieldAccessLevel,
            FieldPermissionRule,
            FieldVisibility,
            RoleDefinition,
            RoleType,
            field_permission_manager,
            role_manager,
        )

        _SECURITY_COMPONENTS = {
            "FieldAccessLevel": FieldAccessLevel,
            "FieldPermissionRule": FieldPermissionRule,
            "FieldVisibility": FieldVisibility,
            "RoleDefinition": RoleDefinition,
            "RoleType": RoleType,
            "field_permission_manager": field_permission_manager,
            "role_manager": role_manager,
        }
    return _SECURITY_COMPONENTS


@dataclass
class FilterFieldConfig:
    """
    Declarative configuration for a single filterable field.

    Attributes:
        lookups: List of allowed filter operators (for example: eq, in, between,
                 is_null, icontains). When empty, the generator keeps its
                 default operator set.
        choices: Optional iterable of allowed values (for in filters, enums, etc.).
        help_text: Optional help text to describe the filter when generating docs.
    """

    lookups: list[str] = field(default_factory=list)
    choices: Optional[Sequence[Any]] = None
    help_text: Optional[str] = None


@dataclass
class FilteringConfig:
    """
    Grouped configuration for everything related to filtering.

    Attributes:
        quick: List of field paths that participate in the quick filter.
        quick_lookup: Lookup used for quick filter comparison (default: icontains).
        auto_detect_quick: Whether quick filter fields should be auto-derived when
                           none are provided explicitly.
        fields: Mapping of field names to FilterFieldConfig.
        custom: Mapping of custom filter names to callables or model method names.
    """

    quick: list[str] = field(default_factory=list)
    quick_lookup: str = "icontains"
    auto_detect_quick: bool = True
    fields: dict[str, FilterFieldConfig] = field(default_factory=dict)
    custom: dict[str, Union[str, Callable]] = field(default_factory=dict)


@dataclass
class FieldExposureConfig:
    """
    Configuration for selecting which fields are exposed via GraphQL.

    Attributes:
        include: Optional allow-list; when set only these fields are exposed.
        exclude: Fields to hide entirely from both queries and mutations.
        read_only: Fields only exposed on queries (removed from mutation inputs).
        write_only: Fields only exposed on mutations (hidden from object types).
    """

    include: Optional[list[str]] = None
    exclude: list[str] = field(default_factory=list)
    read_only: list[str] = field(default_factory=list)
    write_only: list[str] = field(default_factory=list)


@dataclass
class OrderingConfig:
    """
    Ordering configuration for list queries.

    Attributes:
        allowed: Allowed field names for order_by (without +/- prefixes).
        default: Default ordering applied when no client value is provided.
        allow_related: Whether related/path based ordering is permitted.
    """

    allowed: list[str] = field(default_factory=list)
    default: list[str] = field(default_factory=list)
    allow_related: bool = True


@dataclass
class ResolverConfig:
    """
    Custom resolver registration.

    Attributes:
        queries: Mapping of resolver slots (e.g. "list", "retrieve", "custom_name")
                 to callables or method names.
        mutations: Mapping of mutation names to callables/method names.
        fields: Mapping of field names to custom resolver callables.
    """

    queries: dict[str, Union[str, Callable]] = field(default_factory=dict)
    mutations: dict[str, Union[str, Callable]] = field(default_factory=dict)
    fields: dict[str, Union[str, Callable]] = field(default_factory=dict)


@dataclass
class RoleConfig:
    """Declarative role configuration scoped to a GraphQL model."""

    name: str = ""
    description: str = ""
    role_type: str = "business"
    permissions: list[str] = field(default_factory=list)
    parent_roles: list[str] = field(default_factory=list)
    is_system_role: bool = False
    max_users: Optional[int] = None


@dataclass
class OperationGuardConfig:
    """
    Operation-level guard definition.
    """

    name: str = ""
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    condition: Optional[Union[str, Callable]] = None
    require_authentication: bool = True
    allow_anonymous: bool = False
    match: str = "any"  # 'any' or 'all'
    deny_message: Optional[str] = None


@dataclass
class FieldGuardConfig:
    """
    Field-level guard definition.
    """

    field: str
    access: str = "read"
    visibility: str = "visible"
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    mask_value: Any = None
    condition: Optional[Union[str, Callable]] = None


@dataclass
class AccessControlConfig:
    """
    Access control configuration bundle.
    """

    roles: dict[str, RoleConfig] = field(default_factory=dict)
    operations: dict[str, OperationGuardConfig] = field(default_factory=dict)
    fields: list[FieldGuardConfig] = field(default_factory=list)


@dataclass
class ClassificationConfig:
    """
    Data classification tags for a model and its fields.
    """

    model: list[str] = field(default_factory=list)
    fields: dict[str, list[str]] = field(default_factory=dict)


class GraphQLMeta:
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

        self.filtering: FilteringConfig = self._build_filtering_config()
        self.field_config: FieldExposureConfig = self._build_field_config()
        self.ordering_config: OrderingConfig = self._build_ordering_config()
        self.resolvers: ResolverConfig = self._build_resolver_config()
        self.access_config: AccessControlConfig = self._build_access_control_config()
        self.classification_config: ClassificationConfig = (
            self._build_classification_config()
        )

        # Backwards-compatible attribute aliases
        self.custom_filters = self.filtering.custom
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

    def _resolve_meta_class(self, model_class: type[models.Model]) -> Any:
        """Return the declared GraphQL meta configuration class if it exists."""

        meta_decl = getattr(model_class, "GraphQLMeta", None) or getattr(
            model_class, "GraphqlMeta", None
        )
        if meta_decl is not None:
            return meta_decl
        try:
            from .meta_json import get_model_meta_config

            return get_model_meta_config(model_class)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Could not load JSON GraphQLMeta for %s: %s",
                model_class.__name__,
                exc,
            )
            return None

    def _build_filtering_config(self) -> FilteringConfig:
        """Construct filtering configuration with legacy fallbacks."""

        if not self._meta_config:
            return FilteringConfig()

        raw = getattr(self._meta_config, "filtering", None)
        if isinstance(raw, FilteringConfig):
            config = FilteringConfig(
                quick=list(raw.quick),
                quick_lookup=raw.quick_lookup,
                auto_detect_quick=raw.auto_detect_quick,
                fields={
                    name: self._coerce_filter_field_config(value)
                    for name, value in raw.fields.items()
                },
                custom=dict(raw.custom),
            )
        elif isinstance(raw, dict):
            config = FilteringConfig(
                quick=list(raw.get("quick", [])),
                quick_lookup=raw.get("quick_lookup", "icontains"),
                auto_detect_quick=raw.get("auto_detect_quick", True),
                fields={
                    name: self._coerce_filter_field_config(value)
                    for name, value in raw.get("fields", {}).items()
                },
                custom=dict(raw.get("custom", {})),
            )
        else:
            config = FilteringConfig()

        if not config.custom:
            legacy_custom = getattr(self._meta_config, "custom_filters", {})
            if isinstance(legacy_custom, dict):
                config.custom = dict(legacy_custom)

        if not config.quick:
            legacy_quick = getattr(self._meta_config, "quick_filter_fields", None)
            if legacy_quick:
                config.quick = list(legacy_quick)

        legacy_filters = getattr(self._meta_config, "filters", {})
        if isinstance(legacy_filters, dict):
            for name, value in legacy_filters.items():
                config.fields.setdefault(name, self._coerce_filter_field_config(value))

        legacy_filter_fields = getattr(self._meta_config, "filter_fields", {})
        if isinstance(legacy_filter_fields, dict):
            for name, value in legacy_filter_fields.items():
                if name == "quick" and not config.quick:
                    if isinstance(value, (list, tuple)):
                        config.quick = list(value)
                    elif isinstance(value, str):
                        config.quick = [value]
                    continue
                config.fields.setdefault(name, self._coerce_filter_field_config(value))

        return config

    def _build_field_config(self) -> FieldExposureConfig:
        """Construct field exposure configuration."""

        if not self._meta_config:
            return FieldExposureConfig()

        raw = getattr(self._meta_config, "fields", None)
        if isinstance(raw, FieldExposureConfig):
            return FieldExposureConfig(
                include=list(raw.include) if raw.include else None,
                exclude=list(raw.exclude),
                read_only=list(raw.read_only),
                write_only=list(raw.write_only),
            )
        if isinstance(raw, dict):
            include = raw.get("include")
            if include is not None:
                include = list(include)
            return FieldExposureConfig(
                include=include,
                exclude=list(raw.get("exclude", [])),
                read_only=list(raw.get("read_only", [])),
                write_only=list(raw.get("write_only", [])),
            )

        include_fields = getattr(self._meta_config, "include_fields", None)
        if include_fields is not None:
            include_fields = list(include_fields)

        return FieldExposureConfig(
            include=include_fields,
            exclude=list(getattr(self._meta_config, "exclude_fields", [])),
        )

    def _build_ordering_config(self) -> OrderingConfig:
        """Construct ordering configuration.

        This method builds the ordering configuration from the model's GraphQLMeta
        if present. When no explicit GraphQL ordering is provided, it falls back
        to a safe default derived from the Django model's Meta:
        - Use Meta.ordering when defined
        - Else use descending latest_by if configured ("-<latest_by>")
        - Else default to descending primary key ("-id" or "-<pk field name>")

        The goal is to ensure deterministic results and align with the common
        expectation that newest records appear first by default.
        """

        # Build from GraphQLMeta if present
        config: OrderingConfig
        if self._meta_config:
            raw = getattr(self._meta_config, "ordering", None)
            if isinstance(raw, OrderingConfig):
                config = OrderingConfig(
                    allowed=list(raw.allowed),
                    default=list(raw.default),
                    allow_related=raw.allow_related,
                )
            elif isinstance(raw, dict):
                config = OrderingConfig(
                    allowed=list(raw.get("allowed", [])),
                    default=list(raw.get("default", [])),
                    allow_related=raw.get("allow_related", True),
                )
            elif isinstance(raw, (list, tuple)):
                values = list(raw)
                config = OrderingConfig(allowed=values, default=values)
            else:
                config = OrderingConfig()
        else:
            config = OrderingConfig()

        # Fallbacks when no explicit default ordering is provided
        if not config.default:
            model_meta = getattr(self.model_class, "_meta", None)
            fallback_default: list[str] = []

            try:
                # 1) Use Django Meta.ordering if available
                if model_meta and getattr(model_meta, "ordering", None):
                    fallback_default = list(model_meta.ordering)
                # 2) Else use latest_by (descending)
                elif model_meta and getattr(model_meta, "get_latest_by", None):
                    fallback_default = [f"-{model_meta.get_latest_by}"]
                else:
                    # 3) Else use descending primary key
                    pk_name = (
                        model_meta.pk.name
                        if model_meta and getattr(model_meta, "pk", None)
                        else "id"
                    )
                    fallback_default = [f"-{pk_name}"]
            except Exception:
                # Fail-safe fallback if model meta inspection fails
                fallback_default = ["-id"]

            # If an allow-list is defined and does not include the fallback fields,
            # choose the first allowed field to avoid invalid default configuration.
            if config.allowed:
                fallback_names = [f.lstrip("-") for f in fallback_default]
                allowed_set = set(config.allowed)
                if not all(name in allowed_set for name in fallback_names):
                    # Prefer descending for deterministic "latest first" semantics
                    safe_default = [f"-{config.allowed[0]}"]
                    config.default = safe_default
                else:
                    config.default = fallback_default
            else:
                config.default = fallback_default

        return config

    def _build_resolver_config(self) -> ResolverConfig:
        """Construct resolver configuration."""

        if not self._meta_config:
            return ResolverConfig()

        raw = getattr(self._meta_config, "resolvers", None)
        if isinstance(raw, ResolverConfig):
            return ResolverConfig(
                queries=dict(raw.queries),
                mutations=dict(raw.mutations),
                fields=dict(raw.fields),
            )
        if isinstance(raw, dict):
            return ResolverConfig(
                queries=dict(raw.get("queries", {})),
                mutations=dict(raw.get("mutations", {})),
                fields=dict(raw.get("fields", {})),
            )

        legacy_resolvers = getattr(self._meta_config, "custom_resolvers", {})
        if isinstance(legacy_resolvers, dict):
            return ResolverConfig(queries=dict(legacy_resolvers))

        return ResolverConfig()

    def _build_access_control_config(self) -> AccessControlConfig:
        """Construct access control configuration."""

        if not self._meta_config:
            return AccessControlConfig()

        raw = getattr(self._meta_config, "access", None)
        if isinstance(raw, AccessControlConfig):
            roles = {
                name: self._coerce_role_config(name, role)
                for name, role in raw.roles.items()
            }
            operations = {
                name: self._coerce_operation_guard(name, guard)
                for name, guard in raw.operations.items()
            }
            fields = [self._coerce_field_guard(guard) for guard in raw.fields]
            return AccessControlConfig(
                roles=roles, operations=operations, fields=fields
            )

        if isinstance(raw, dict):
            roles = {}
            for name, cfg in (raw.get("roles") or {}).items():
                roles[name] = self._coerce_role_config(name, cfg)

            operations = {}
            for name, cfg in (raw.get("operations") or {}).items():
                operations[name] = self._coerce_operation_guard(name, cfg)

            field_guards = [
                self._coerce_field_guard(cfg) for cfg in raw.get("fields", [])
            ]
            return AccessControlConfig(
                roles=roles, operations=operations, fields=field_guards
            )

        return AccessControlConfig()

    def _build_classification_config(self) -> ClassificationConfig:
        """Construct classification tags for the model."""

        if not self._meta_config:
            return ClassificationConfig()

        raw = getattr(self._meta_config, "classifications", None)
        if raw is None:
            raw = getattr(self._meta_config, "classification", None)
        if raw is None:
            raw = getattr(self._meta_config, "data_classification", None)

        if isinstance(raw, ClassificationConfig):
            return ClassificationConfig(
                model=list(raw.model),
                fields={name: list(tags) for name, tags in raw.fields.items()},
            )

        if isinstance(raw, (list, tuple, set)):
            return ClassificationConfig(model=[str(tag) for tag in raw if tag])

        if isinstance(raw, dict):
            model_tags = raw.get("model") or raw.get("tags") or raw.get("model_tags")
            if model_tags is None:
                model_tags = raw.get("classifications") or []
            field_tags = raw.get("fields") or raw.get("field_tags") or {}
            normalized_fields = {}
            for field_name, tags in field_tags.items():
                if not field_name:
                    continue
                if isinstance(tags, (list, tuple, set)):
                    normalized_fields[field_name] = [str(tag) for tag in tags if tag]
                elif tags:
                    normalized_fields[field_name] = [str(tags)]
            return ClassificationConfig(
                model=[str(tag) for tag in model_tags or [] if tag],
                fields=normalized_fields,
            )

        return ClassificationConfig()

    def _coerce_role_config(self, name: str, value: Any) -> RoleConfig:
        if isinstance(value, RoleConfig):
            if not value.name:
                value.name = name
            return value
        if isinstance(value, dict):
            return RoleConfig(
                name=value.get("name") or name,
                description=value.get("description", ""),
                role_type=self._coerce_role_type(value.get("role_type")),
                permissions=list(value.get("permissions", [])),
                parent_roles=list(value.get("parent_roles", [])),
                is_system_role=value.get("is_system_role", False),
                max_users=value.get("max_users"),
            )
        raise ValueError(f"Unsupported role configuration for '{name}': {value}")

    def _coerce_operation_guard(self, name: str, value: Any) -> OperationGuardConfig:
        if isinstance(value, OperationGuardConfig):
            if not value.name:
                value.name = name
            return value
        if isinstance(value, dict):
            return OperationGuardConfig(
                name=name,
                roles=list(value.get("roles", [])),
                permissions=list(value.get("permissions", [])),
                condition=value.get("condition"),
                require_authentication=value.get("require_authentication", True),
                allow_anonymous=value.get("allow_anonymous", False),
                match=value.get("match", "any"),
                deny_message=value.get("deny_message"),
            )
        if isinstance(value, (list, tuple)):
            # Treat list as roles shortcut
            return OperationGuardConfig(name=name, roles=list(value))
        raise ValueError(
            f"Unsupported operation guard configuration for '{name}': {value}"
        )

    def _coerce_field_guard(self, value: Any) -> FieldGuardConfig:
        if isinstance(value, FieldGuardConfig):
            return value
        if isinstance(value, dict):
            return FieldGuardConfig(
                field=value.get("field"),
                access=value.get("access", "read"),
                visibility=value.get("visibility", "visible"),
                roles=list(value.get("roles", [])),
                permissions=list(value.get("permissions", [])),
                mask_value=value.get("mask") or value.get("mask_value"),
                condition=value.get("condition"),
            )
        raise ValueError(f"Unsupported field guard configuration: {value}")

    def _coerce_role_type(self, role_type: Any) -> str:
        if isinstance(role_type, str) and role_type.strip():
            return role_type.strip().lower()
        return "business"

    def _convert_role_type(self, value: str, role_type_cls: Any):
        normalized = (value or "business").strip().lower()
        for candidate in role_type_cls:
            if candidate.value == normalized or candidate.name.lower() == normalized:
                return candidate
        return getattr(role_type_cls, "BUSINESS", list(role_type_cls)[0])

    def _index_operation_guards(self) -> dict[str, OperationGuardConfig]:
        guards: dict[str, OperationGuardConfig] = {}
        for name, guard in self.access_config.operations.items():
            guards[name] = (
                guard
                if isinstance(guard, OperationGuardConfig)
                else self._coerce_operation_guard(name, guard)
            )
        return guards

    def _register_roles(self) -> None:
        components = _load_security_components()
        RoleDefinition = components["RoleDefinition"]
        role_mgr = components["role_manager"]
        RoleTypeCls = components["RoleType"]
        for role in self.access_config.roles.values():
            try:
                role_definition = RoleDefinition(
                    name=role.name,
                    description=role.description,
                    role_type=self._convert_role_type(role.role_type, RoleTypeCls),
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
        components = _load_security_components()
        FieldPermissionRule = components["FieldPermissionRule"]
        field_permission_mgr = components["field_permission_manager"]
        for guard in self.access_config.fields:
            if not guard.field:
                continue
            access_level = self._coerce_access_level(guard.access, components)
            visibility = self._coerce_visibility(guard.visibility, components)
            condition = self._resolve_condition_callable(guard.condition)
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
        components = _load_security_components()
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

    def _coerce_access_level(self, value: str, components: dict[str, Any]):
        FieldAccessLevel = components["FieldAccessLevel"]
        if isinstance(value, FieldAccessLevel):
            return value
        mapping = {
            "none": FieldAccessLevel.NONE,
            "read": FieldAccessLevel.READ,
            "write": FieldAccessLevel.WRITE,
            "admin": FieldAccessLevel.ADMIN,
        }
        return mapping.get(str(value).lower(), FieldAccessLevel.READ)

    def _coerce_visibility(self, value: str, components: dict[str, Any]):
        FieldVisibility = components["FieldVisibility"]
        if isinstance(value, FieldVisibility):
            return value
        mapping = {
            "visible": FieldVisibility.VISIBLE,
            "hidden": FieldVisibility.HIDDEN,
            "masked": FieldVisibility.MASKED,
            "redacted": FieldVisibility.REDACTED,
        }
        return mapping.get(str(value).lower(), FieldVisibility.VISIBLE)

    def _resolve_condition_callable(
        self, condition: Optional[Union[str, Callable]]
    ) -> Optional[Callable]:
        if condition is None:
            return None
        if callable(condition):
            return condition
        if isinstance(condition, str) and hasattr(self.model_class, condition):
            candidate = getattr(self.model_class, condition)
            if callable(candidate):
                return candidate
        return None

    def _coerce_filter_field_config(self, value: Any) -> FilterFieldConfig:
        """Normalize legacy filter definitions into FilterFieldConfig."""

        if isinstance(value, FilterFieldConfig):
            return FilterFieldConfig(
                lookups=list(value.lookups),
                choices=list(value.choices) if value.choices is not None else None,
                help_text=value.help_text,
            )

        if value is None:
            return FilterFieldConfig()

        if isinstance(value, (list, tuple, set)):
            return FilterFieldConfig(lookups=list(value))

        if isinstance(value, str):
            return FilterFieldConfig(lookups=[value])

        if isinstance(value, dict):
            choices = value.get("choices")
            help_text = value.get("help_text")

            if "lookups" in value:
                lookups = value.get("lookups") or []
            else:
                lookups: list[str] = []
                for lookup, definition in value.items():
                    if lookup in {"choices", "help_text"}:
                        continue
                    if isinstance(definition, bool):
                        if definition:
                            lookups.append(lookup)
                    else:
                        lookups.append(lookup)
                        if (
                            lookup == "in"
                            and choices is None
                            and isinstance(definition, (list, tuple, set))
                        ):
                            choices = list(definition)

            if isinstance(choices, (list, tuple, set)):
                choices = list(choices)

            return FilterFieldConfig(
                lookups=list(lookups),
                choices=choices,
                help_text=help_text,
            )

        return FilterFieldConfig()

    def _validate_configuration(self) -> None:
        """Validate quick filter paths and ensure referenced fields exist."""

        for field_path in self.quick_filter_fields:
            self._validate_field_path(field_path)

        for field_name in self.filtering.fields.keys():
            self._validate_field_path(field_name)

    def _validate_field_path(self, field_path: str) -> None:
        """
        Validate that a field path exists on the model.

        Args:
            field_path: Field path to validate (e.g., 'name', 'profile__bio')

        Raises:
            ValueError: If field path is invalid
        """

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
                                f"Field '{field_name}' in path '{field_path}' is not a relation"
                            )
                except FieldDoesNotExist as exc:
                    raise ValueError(
                        f"Field '{field_name}' does not exist on model {current_model.__name__}"
                    ) from exc

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Could not validate field path '%s' on model %s: %s",
                field_path,
                self.model_class.__name__,
                exc,
            )

    def ensure_operation_access(
        self,
        operation: str,
        info: Any,
        *,
        instance: Optional[models.Model] = None,
    ) -> None:
        """
        Enforce the configured access guard for a given operation.

        Raises:
            GraphQLError when the current user is not allowed to perform the operation.
        """

        guard = self._operation_guards.get(operation) or self._operation_guards.get("*")
        if not guard:
            return

        security = _load_security_components()
        role_mgr = security["role_manager"]

        context = getattr(info, "context", None)
        user = getattr(context, "user", None)

        if guard.allow_anonymous:
            return

        if guard.require_authentication and not (user and user.is_authenticated):
            raise GraphQLError(
                guard.deny_message
                or f"Authentication required to perform '{operation}' on {self.model_class.__name__}"
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
            condition_callable = self._resolve_condition_callable(guard.condition)
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
            # No specific roles/permissions/conditions configured -> auth check already performed.
            return

        if guard.match.lower() == "all":
            allowed = all(criteria_results)
        else:
            allowed = any(criteria_results)

        if not allowed:
            raise GraphQLError(
                guard.deny_message
                or f"Operation '{operation}' is not permitted on {self.model_class.__name__}"
            )

    def describe_operation_guard(
        self,
        operation: str,
        *,
        user: Optional[Any] = None,
        instance: Optional[models.Model] = None,
    ) -> dict[str, Any]:
        """
        Evaluate the configured access guard for a given operation without raising.

        Returns a dictionary describing whether the guard allowed access and any reason otherwise.
        """
        guard = self._operation_guards.get(operation) or self._operation_guards.get("*")
        if not guard:
            return {"guarded": False, "allowed": True, "reason": None}

        security = _load_security_components()
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
            condition_callable = self._resolve_condition_callable(guard.condition)
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
            field_name: Name of the field to evaluate.
            for_input: True when evaluating mutation/input exposure.
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
            Dictionary mapping field names to allowed lookups.
        """

        return {
            name: cfg.lookups[:] if cfg.lookups else []
            for name, cfg in self.filtering.fields.items()
        }

    def get_ordering_fields(self) -> list[str]:
        """
        Get the ordering fields configuration.
        """

        if self.ordering_config.allowed:
            return list(self.ordering_config.allowed)
        if self.ordering_config.default:
            return list(self.ordering_config.default)
        return []

    def has_custom_resolver(self, resolver_name: str) -> bool:
        """Check if a custom resolver exists."""

        return resolver_name in self.custom_resolvers

    def has_custom_filter(self, filter_name: str) -> bool:
        """Check if a custom filter exists."""

        return filter_name in self.custom_filters

    def has_quick_filter(self) -> bool:
        """Check if quick filter is configured."""

        return bool(self.quick_filter_fields)


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
