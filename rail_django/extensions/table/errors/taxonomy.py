"""Table error taxonomy."""

from __future__ import annotations

from enum import Enum


class TableErrorCode(str, Enum):
    UNKNOWN = "TABLE_UNKNOWN"
    VALIDATION = "TABLE_VALIDATION"
    NOT_FOUND = "TABLE_NOT_FOUND"
    RATE_LIMIT = "TABLE_RATE_LIMIT"
    PERMISSION = "TABLE_PERMISSION"
    CONFLICT = "TABLE_CONFLICT"
