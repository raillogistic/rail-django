"""
GraphQL Meta Configuration Dataclasses

This module contains all the configuration dataclasses used by GraphQLMeta
to define filtering, field exposure, ordering, resolvers, access control,
and other declarative settings for Django models in GraphQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence, Union


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
    presets: dict[str, dict[str, Any]] = field(default_factory=dict)


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


@dataclass
class PipelineConfig:
    """
    Configuration for mutation pipeline customization.

    Allows models to customize the mutation pipeline by adding, removing,
    or reordering steps.

    Attributes:
        extra_steps: List of extra step classes to add to all pipelines
        skip_steps: List of step names to skip
        step_order: Dict mapping step names to custom order values
        create_steps: List of extra step classes for create mutations only
        update_steps: List of extra step classes for update mutations only
        delete_steps: List of extra step classes for delete mutations only
    """

    extra_steps: list[type] = field(default_factory=list)
    skip_steps: list[str] = field(default_factory=list)
    step_order: dict[str, int] = field(default_factory=dict)
    create_steps: list[type] = field(default_factory=list)
    update_steps: list[type] = field(default_factory=list)
    delete_steps: list[type] = field(default_factory=list)


@dataclass
class RelationOperationConfig:
    """Configuration for a specific relation operation (e.g. connect, create)."""
    enabled: bool = True
    require_permission: Optional[str] = None


@dataclass
class FieldRelationConfig:
    """Configuration for a relationship field's operations."""
    style: str = "unified"  # unified, id_only
    connect: RelationOperationConfig = field(default_factory=lambda: RelationOperationConfig(enabled=True))
    create: RelationOperationConfig = field(default_factory=lambda: RelationOperationConfig(enabled=True))
    update: RelationOperationConfig = field(default_factory=lambda: RelationOperationConfig(enabled=True))
    disconnect: RelationOperationConfig = field(default_factory=lambda: RelationOperationConfig(enabled=True))
    set: RelationOperationConfig = field(default_factory=lambda: RelationOperationConfig(enabled=True))
