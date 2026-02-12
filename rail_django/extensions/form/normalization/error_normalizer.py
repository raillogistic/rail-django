"""
Normalize generated form errors to a single backend contract.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from ..config import DEFAULT_FORM_ERROR_KEY
from ..utils.pathing import build_bulk_row_path, normalize_path

ErrorSource = str


def _as_error_dict(
    *,
    field: str | None,
    message: Any,
    code: str | None = None,
    source: ErrorSource = "OPERATION",
    row_index: int | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_field = normalize_path(field) or DEFAULT_FORM_ERROR_KEY
    return {
        "field": normalized_field,
        "message": str(message),
        "code": code,
        "source": source,
        "row_index": row_index,
        "meta": meta,
    }


def _flatten_validation_error(
    value: Any,
    *,
    prefix: str | None = None,
    source: ErrorSource = "OPERATION",
    row_index: int | None = None,
) -> list[dict[str, Any]]:
    if isinstance(value, ValidationError):
        if hasattr(value, "message_dict"):
            output: list[dict[str, Any]] = []
            for field, messages in value.message_dict.items():
                field_prefix = normalize_path(field if field != "__all__" else prefix)
                output.extend(
                    _flatten_validation_error(
                        messages,
                        prefix=field_prefix,
                        source=source,
                        row_index=row_index,
                    )
                )
            return output
        if hasattr(value, "messages"):
            return [
                _as_error_dict(
                    field=prefix,
                    message=message,
                    code=getattr(value, "code", None),
                    source=source,
                    row_index=row_index,
                )
                for message in value.messages
            ]

    if isinstance(value, dict):
        flattened: list[dict[str, Any]] = []
        for field, messages in value.items():
            next_prefix = normalize_path(field if field != "__all__" else prefix)
            flattened.extend(
                _flatten_validation_error(
                    messages,
                    prefix=next_prefix,
                    source=source,
                    row_index=row_index,
                )
            )
        return flattened

    if isinstance(value, (list, tuple)):
        flattened: list[dict[str, Any]] = []
        for item in value:
            flattened.extend(
                _flatten_validation_error(
                    item,
                    prefix=prefix,
                    source=source,
                    row_index=row_index,
                )
            )
        return flattened

    return [
        _as_error_dict(
            field=prefix,
            message=value,
            source=source,
            row_index=row_index,
        )
    ]


def normalize_mutation_errors(
    errors: Any,
    *,
    source: ErrorSource = "OPERATION",
    default_field: str = DEFAULT_FORM_ERROR_KEY,
) -> list[dict[str, Any]]:
    if errors is None:
        return []
    if isinstance(errors, ValidationError):
        return _flatten_validation_error(errors, prefix=default_field, source=source)
    if isinstance(errors, str):
        return [_as_error_dict(field=default_field, message=errors, source=source)]

    normalized: list[dict[str, Any]] = []
    if not isinstance(errors, (list, tuple)):
        errors = [errors]
    for error in errors:
        if isinstance(error, dict):
            normalized.append(
                _as_error_dict(
                    field=error.get("field") or default_field,
                    message=error.get("message", "An unexpected error occurred."),
                    code=error.get("code"),
                    source=str(error.get("source") or source).upper(),
                    row_index=error.get("row_index"),
                    meta=error.get("meta"),
                )
            )
            continue
        if isinstance(error, ValidationError):
            normalized.extend(
                _flatten_validation_error(error, prefix=default_field, source=source)
            )
            continue
        normalized.append(
            _as_error_dict(field=default_field, message=error, source=source)
        )
    return normalized


def normalize_bulk_errors(
    row_errors: list[dict[str, Any]],
    *,
    source: ErrorSource = "OPERATION",
    row_prefix: str = "items",
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row_error in row_errors or []:
        row_index = row_error.get("row_index")
        field = row_error.get("field")
        message = row_error.get("message", "Bulk operation failed.")
        code = row_error.get("code")
        meta = row_error.get("meta")

        normalized.append(
            _as_error_dict(
                field=build_bulk_row_path(field, row_index, prefix=row_prefix),
                message=message,
                code=code,
                source=str(row_error.get("source") or source).upper(),
                row_index=row_index,
                meta=meta,
            )
        )
    return normalized
