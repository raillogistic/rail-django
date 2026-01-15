"""
Mutation error helpers.
"""

from typing import Any, Dict, List, Optional, Type
import re

import graphene
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models


class MutationError(graphene.ObjectType):
    """
    Structured error type for GraphQL mutations.

    Attributes:
        field: The field name where the error occurred (optional)
        message: The error message describing what went wrong
    """

    field = graphene.String(description="Le nom du champ oÇû l'erreur s'est produite")
    message = graphene.String(
        required=False,
        description="Le message dÇ¸crivant ce qui s'est mal passÇ¸",
    )


def _normalize_field_path(field: Any, prefix: Optional[str] = None) -> Optional[str]:
    """
    Convert backend field identifiers (including dotted, double-underscore or list
    index notations) to a consistent dot-separated path understood by the frontend.
    """
    if field is None:
        return prefix

    segment = str(field)
    segment = segment.replace("__", ".")
    segment = segment.replace("[", ".").replace("]", "")
    segment = segment.replace("..", ".").strip(".")
    if prefix:
        return f"{prefix}.{segment}".strip(".")
    return segment or None


def _flatten_validation_error(
    detail: Any, path: Optional[str], accumulator: list[MutationError]
) -> None:
    """
    Recursively flatten Django ValidationError payloads (dict/list/ValidationError)
    into a flat list of MutationError objects with normalized field paths.
    """
    if isinstance(detail, ValidationError):
        if hasattr(detail, "message_dict") and isinstance(detail.message_dict, dict):
            for field_name, messages in detail.message_dict.items():
                next_path = _normalize_field_path(field_name, path)
                _flatten_validation_error(messages, next_path, accumulator)
            return
        if hasattr(detail, "error_dict") and isinstance(detail.error_dict, dict):
            for field_name, messages in detail.error_dict.items():
                next_path = _normalize_field_path(field_name, path)
                _flatten_validation_error(messages, next_path, accumulator)
            return
        messages = (
            detail.messages
            if hasattr(detail, "messages") and isinstance(detail.messages, list)
            else [str(detail)]
        )
        for message in messages:
            accumulator.append(MutationError(field=path, message=str(message)))
        return

    if isinstance(detail, dict):
        for field_name, messages in detail.items():
            next_path = _normalize_field_path(field_name, path)
            _flatten_validation_error(messages, next_path, accumulator)
        return

    if isinstance(detail, (list, tuple)):
        for index, item in enumerate(detail):
            next_path = path
            if isinstance(item, (dict, list, ValidationError)):
                next_path = _normalize_field_path(index, path)
            _flatten_validation_error(item, next_path, accumulator)
        return

    accumulator.append(MutationError(field=path, message=str(detail)))


def build_validation_errors(
    error: ValidationError, prefix: Optional[str] = None
) -> list[MutationError]:
    """Convert a ValidationError into a flat list of MutationError objects."""
    collected: list[MutationError] = []
    _flatten_validation_error(error, prefix, collected)
    return collected


def build_mutation_error(message: str, field: Optional[str] = None) -> MutationError:
    """Helper to build a single MutationError with a normalized field path."""
    return MutationError(field=_normalize_field_path(field), message=str(message))


def _extract_field_from_message(message: str) -> Optional[str]:
    match = re.search(r"Required field '([^']+)'", message)
    if match:
        return match.group(1)
    match = re.search(r"Field '([^']+)'", message)
    if match:
        return match.group(1)
    match = re.search(r"field '([^']+)'", message)
    if match:
        return match.group(1)
    return None


def build_error_list(messages: list[str]) -> list[MutationError]:
    """Convert plain error messages into MutationError objects."""
    errors: list[MutationError] = []
    for message in messages:
        field = _extract_field_from_message(str(message))
        errors.append(build_mutation_error(message=str(message), field=field))
    return errors


def _map_column_to_field(model: type[models.Model], column: str) -> Optional[str]:
    for field in model._meta.get_fields():
        if hasattr(field, "column") and field.column == column:
            return field.name
        if getattr(field, "attname", None) == column:
            return field.name
    return None


def _get_field_label(model: type[models.Model], field_name: str) -> str:
    try:
        field = model._meta.get_field(field_name)
        label = getattr(field, "verbose_name", None)
        if label:
            return str(label)
    except Exception:
        pass
    return field_name


def _extract_unique_constraint_fields(
    model: type[models.Model], error_msg: str
) -> list[str]:
    fields: list[str] = []

    match = re.search(r"UNIQUE constraint failed: ([\\w\\., ]+)", error_msg)
    if match:
        cols = [part.strip() for part in match.group(1).split(",")]
        for col in cols:
            col_name = col.split(".")[-1]
            fields.append(_map_column_to_field(model, col_name) or col_name)

    if not fields:
        match = re.search(r"Key \\(([^\\)]+)\\)=\\([^\\)]+\\) already exists", error_msg)
        if match:
            cols = [c.strip() for c in match.group(1).split(",")]
            for col_name in cols:
                fields.append(_map_column_to_field(model, col_name) or col_name)

    if not fields:
        match = re.search(r"Duplicate entry .* for key '([^']+)'", error_msg)
        if match:
            fields.append(match.group(1))

    return fields


def _extract_not_null_field(error_msg: str) -> Optional[str]:
    match = re.search(
        r'null value in column "([^"]+)" violates not-null constraint', error_msg
    )
    if match:
        return match.group(1)
    match = re.search(r"NOT NULL constraint failed: ([\\w\\.]+)", error_msg)
    if match:
        return match.group(1).split(".")[-1]
    match = re.search(r"Column '([^']+)' cannot be null", error_msg)
    if match:
        return match.group(1)
    return None


def build_integrity_errors(
    model: type[models.Model], exc: IntegrityError
) -> list[MutationError]:
    """Create friendly errors for database integrity failures."""
    error_msg = str(exc)
    field = _extract_not_null_field(error_msg)
    if field:
        field_name = _map_column_to_field(model, field) or field
        label = _get_field_label(model, field_name)
        return [build_mutation_error(f"{label} cannot be null.", field_name)]

    unique_fields = _extract_unique_constraint_fields(model, error_msg)
    if unique_fields:
        errors: list[MutationError] = []
        for field_name in unique_fields:
            label = _get_field_label(model, field_name)
            errors.append(build_mutation_error(f"{label} must be unique.", field_name))
        return errors

    lower_msg = error_msg.lower()
    if "duplicate key value violates unique constraint" in lower_msg:
        return [
            build_mutation_error("Duplicate value violates unique constraint.", None)
        ]
    if "unique constraint" in lower_msg or "duplicate entry" in lower_msg:
        return [
            build_mutation_error("Duplicate value violates unique constraint.", None)
        ]
    if "foreign key constraint" in lower_msg:
        return [
            build_mutation_error(
                "Invalid reference: related object does not exist.", None
            )
        ]
    if "check constraint" in lower_msg:
        return [build_mutation_error("Value violates a database constraint.", None)]

    return [build_mutation_error("Database integrity error.", None)]
