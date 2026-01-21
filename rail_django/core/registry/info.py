"""
SchemaInfo model.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SchemaInfo:
    """Information about a registered schema."""

    name: str
    description: str = ""
    version: str = "1.0.0"
    apps: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    exclude_models: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    schema_class: Optional[type] = None
    builder: Optional[Any] = None
    auto_discover: bool = True
    enabled: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
