"""
Configuration dataclasses for per-field relation operation control.
"""

from dataclasses import dataclass, field
from typing import Optional

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
