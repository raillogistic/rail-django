"""Input validation and sanitization for table payloads."""

from __future__ import annotations

import re

SCRIPT_PATTERN = re.compile(r"<\s*script", re.IGNORECASE)


def sanitize_text(value: str) -> str:
    sanitized = SCRIPT_PATTERN.sub("", value)
    return sanitized.replace("<", "").replace(">", "")


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    for key, value in payload.items():
        if key.startswith("$"):
            errors.append(f"Invalid key '{key}'")
        if isinstance(value, str) and SCRIPT_PATTERN.search(value):
            errors.append(f"Potential script injection in '{key}'")
    return errors
