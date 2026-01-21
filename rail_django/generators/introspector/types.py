"""
Data structures for introspection results.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FieldInfo:
    """Stores metadata about a Django model field."""
    field_type: Any
    is_required: bool
    default_value: Any
    help_text: str
    has_auto_now: bool = False
    has_auto_now_add: bool = False
    blank: bool = True
    has_default: bool = False


@dataclass
class RelationshipInfo:
    """Stores metadata about a model relationship."""
    related_model: Any
    relationship_type: str
    to_field: Optional[str]
    from_field: str


@dataclass
class MethodInfo:
    """Information about a model method."""
    name: str
    arguments: dict[str, Any]
    return_type: Any
    is_async: bool
    is_mutation: bool = False
    is_private: bool = False
    method: Any = None


@dataclass
class PropertyInfo:
    """Stores metadata about a model property."""
    return_type: Any
    verbose_name: Optional[str] = None


@dataclass
class ManagerInfo:
    """Stores metadata about a Django model manager."""
    name: str
    manager_class: type
    is_default: bool = False
    custom_methods: dict[str, Any] = field(default_factory=dict)


@dataclass
class InheritanceInfo:
    """Stores metadata about model inheritance."""
    base_classes: list[Any]
    is_abstract: bool
