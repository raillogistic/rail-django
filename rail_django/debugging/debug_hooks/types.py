"""
Debug hooks types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class DebugLevel(Enum):
    """Debug levels for controlling verbosity."""
    NONE = 0
    ERROR = 1
    WARNING = 2
    INFO = 3
    DEBUG = 4
    TRACE = 5


@dataclass
class DebugEvent:
    """Represents a debug event."""
    event_type: str
    timestamp: datetime
    level: DebugLevel
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    error: Optional[Exception] = None
    stack_trace: Optional[str] = None


@dataclass
class DebugSession:
    """Represents a debug session."""
    session_id: str
    start_time: datetime
    events: list[DebugEvent] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
