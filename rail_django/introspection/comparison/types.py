"""
Type definitions for schema comparison.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional


class ChangeType(Enum):
    """Types of schema changes."""
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MODIFIED = "MODIFIED"
    DEPRECATED = "DEPRECATED"
    UNDEPRECATED = "UNDEPRECATED"


class BreakingChangeLevel(Enum):
    """Levels of breaking changes."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class SchemaChange:
    """Represents a change between two schemas."""
    change_type: ChangeType
    element_type: str
    element_path: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    description: str = ""
    breaking_level: BreakingChangeLevel = BreakingChangeLevel.NONE
    migration_notes: str = ""


@dataclass
class SchemaComparison:
    """Result of comparing two schemas."""
    old_schema_name: str
    new_schema_name: str
    old_version: Optional[str] = None
    new_version: Optional[str] = None
    comparison_date: datetime = field(default_factory=datetime.now)
    type_changes: list[SchemaChange] = field(default_factory=list)
    field_changes: list[SchemaChange] = field(default_factory=list)
    argument_changes: list[SchemaChange] = field(default_factory=list)
    directive_changes: list[SchemaChange] = field(default_factory=list)
    total_changes: int = 0
    breaking_changes: int = 0
    non_breaking_changes: int = 0
    breaking_change_level: BreakingChangeLevel = BreakingChangeLevel.NONE
    migration_required: bool = False
    compatibility_score: float = 1.0

    def get_all_changes(self) -> list[SchemaChange]:
        return self.type_changes + self.field_changes + self.argument_changes + self.directive_changes

    def get_breaking_changes(self) -> list[SchemaChange]:
        return [c for c in self.get_all_changes() if c.breaking_level != BreakingChangeLevel.NONE]

    def get_changes_by_type(self, change_type: ChangeType) -> list[SchemaChange]:
        return [c for c in self.get_all_changes() if c.change_type == change_type]

    def to_dict(self) -> dict[str, Any]:
        return {
            'old_schema_name': self.old_schema_name, 'new_schema_name': self.new_schema_name,
            'old_version': self.old_version, 'new_version': self.new_version,
            'comparison_date': self.comparison_date.isoformat(),
            'summary': {'total_changes': self.total_changes, 'breaking_changes': self.breaking_changes, 'non_breaking_changes': self.non_breaking_changes, 'breaking_change_level': self.breaking_change_level.value, 'migration_required': self.migration_required, 'compatibility_score': self.compatibility_score},
            'changes': {'type_changes': [self._change_to_dict(c) for c in self.type_changes], 'field_changes': [self._change_to_dict(c) for c in self.field_changes], 'argument_changes': [self._change_to_dict(c) for c in self.argument_changes], 'directive_changes': [self._change_to_dict(c) for c in self.directive_changes]}
        }

    def _change_to_dict(self, change: SchemaChange) -> dict[str, Any]:
        return {'change_type': change.change_type.value, 'element_type': change.element_type, 'element_path': change.element_path, 'old_value': change.old_value, 'new_value': change.new_value, 'description': change.description, 'breaking_level': change.breaking_level.value, 'migration_notes': change.migration_notes}
