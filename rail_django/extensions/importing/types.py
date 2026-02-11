"""Typed contracts shared across importing services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict


@dataclass(frozen=True)
class ParsedImportFile:
    headers: list[str]
    rows: list[dict[str, Any]]
    file_format: str
    file_name: str
    file_size_bytes: int


@dataclass(frozen=True)
class ImportLimits:
    max_rows: int
    max_file_size_bytes: int


class ImportColumnRule(TypedDict):
    name: str
    label: NotRequired[str | None]
    required: bool
    data_type: str
    default_value: NotRequired[Any | None]
    format_hint: NotRequired[str | None]
    allowed_values: NotRequired[list[str] | None]


class ImportTemplateDescriptor(TypedDict):
    template_id: str
    app_label: str
    model_name: str
    version: str
    exact_version: str
    matching_key_fields: list[str]
    required_columns: list[ImportColumnRule]
    optional_columns: list[ImportColumnRule]
    accepted_formats: list[str]
    max_rows: int
    max_file_size_bytes: int
    download_url: str


class ImportRowPatch(TypedDict):
    row_number: int
    edited_values: dict[str, Any]


class ImportValidationSummary(TypedDict):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    blocking_issues: int
    warnings: int


class ImportSimulationSummary(TypedDict):
    can_commit: bool
    would_create: int
    would_update: int
    blocking_issues: int
    warnings: int
    duration_ms: int


class ImportCommitSummary(TypedDict):
    total_rows: int
    committed_rows: int
    create_rows: int
    update_rows: int
    skipped_rows: int
