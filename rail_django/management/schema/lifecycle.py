"""
Schema lifecycle models and enums.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class SchemaOperation(Enum):
    """Types of schema operations."""
    REGISTER = "register"
    UPDATE = "update"
    DEACTIVATE = "deactivate"
    ACTIVATE = "activate"
    DELETE = "delete"
    MIGRATE = "migrate"
    BACKUP = "backup"
    RESTORE = "restore"


class SchemaStatus(Enum):
    """Schema status values."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    MIGRATING = "migrating"
    ERROR = "error"


@dataclass
class SchemaLifecycleEvent:
    """Represents a schema lifecycle event."""
    event_id: str
    schema_name: str
    operation: SchemaOperation
    timestamp: datetime
    user_id: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None


@dataclass
class SchemaMetadata:
    """Schema metadata information."""
    name: str
    version: str
    description: str
    status: SchemaStatus
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    tags: dict[str, str] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    deprecation_date: Optional[datetime] = None
    migration_path: Optional[str] = None
    backup_enabled: bool = True
    monitoring_enabled: bool = True
