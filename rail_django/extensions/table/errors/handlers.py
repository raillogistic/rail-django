"""Map domain errors to GraphQL-friendly payloads."""

from __future__ import annotations

from .taxonomy import TableErrorCode


def to_error(code: TableErrorCode, message: str, *, retryable: bool = False, details: dict | None = None) -> dict:
    return {
        "field": None,
        "message": message,
        "code": str(code.value if hasattr(code, "value") else code),
        "severity": "error",
        "details": details or {},
        "retryable": retryable,
        "retryAfter": 1 if retryable else None,
        "traceId": None,
    }
