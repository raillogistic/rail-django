"""Field masking helpers for table v3 payloads."""

from __future__ import annotations

from typing import Any, Mapping


def apply_field_masking(
    row: Mapping[str, Any],
    masked_fields: set[str] | dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a copy of ``row`` with masked fields replaced."""
    payload = dict(row)
    if not masked_fields:
        return payload

    if isinstance(masked_fields, dict):
        for field_name, mask_value in masked_fields.items():
            if field_name in payload:
                payload[field_name] = mask_value
        return payload

    for field_name in masked_fields:
        if field_name in payload:
            payload[field_name] = "***"
    return payload
