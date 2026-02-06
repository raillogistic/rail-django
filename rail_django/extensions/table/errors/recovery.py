"""Recovery strategies for retryable table errors."""

from __future__ import annotations


def should_retry(error: dict) -> bool:
    return bool(error.get("retryable"))


def retry_after_seconds(error: dict, default: int = 1) -> int:
    value = error.get("retryAfter")
    return int(value) if isinstance(value, int) else default
