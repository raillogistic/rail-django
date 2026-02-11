"""Row-level validation and issue generation for import batches."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.apps import apps
from django.db import transaction

from ..constants import ImportIssueCode
from ..models import (
    ImportBatch,
    ImportIssue,
    ImportIssueSeverity,
    ImportIssueStage,
    ImportRow,
    ImportRowAction,
    ImportRowStatus,
)
from ..types import ImportTemplateDescriptor


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}


def _is_fk_field(field: Any) -> bool:
    return bool(
        getattr(field, "is_relation", False)
        and getattr(field, "many_to_one", False)
        and not getattr(field, "many_to_many", False)
    )


def _coerce_value(value: Any, field) -> Any:
    internal_type = field.get_internal_type()
    if value in ("", None):
        if getattr(field, "null", False):
            return None
        if field.has_default():
            return field.get_default()
        if internal_type in {
            "CharField",
            "TextField",
            "SlugField",
            "EmailField",
            "URLField",
            "FilePathField",
        }:
            return ""
        return None
    try:
        if internal_type in {"IntegerField", "AutoField", "BigIntegerField", "PositiveIntegerField"}:
            return int(value)
        if internal_type in {"FloatField"}:
            return float(value)
        if internal_type in {"DecimalField"}:
            return str(Decimal(str(value)))
        if internal_type in {"BooleanField", "NullBooleanField"}:
            return _to_bool(value)
        if internal_type in {"ForeignKey", "OneToOneField"}:
            target_field = getattr(field, "target_field", None)
            if target_field is None:
                return value
            return _coerce_value(value, target_field)
        if internal_type == "DateField" and isinstance(value, str):
            return date.fromisoformat(value).isoformat()
        if internal_type == "DateTimeField" and isinstance(value, str):
            return datetime.fromisoformat(value).isoformat()
    except (ValueError, TypeError, InvalidOperation):
        raise
    return value


def _row_error(
    *,
    batch: ImportBatch,
    row: ImportRow,
    row_number: int,
    code: str,
    message: str,
    field_path: str | None = None,
    stage: str = ImportIssueStage.PARSE,
) -> ImportIssue:
    return ImportIssue(
        batch=batch,
        row=row,
        row_number=row_number,
        field_path=field_path,
        code=code,
        severity=ImportIssueSeverity.ERROR,
        message=message,
        stage=stage,
    )


def _validate_row_values(
    *,
    batch: ImportBatch,
    row_number: int,
    edited_values: dict[str, Any],
    descriptor: ImportTemplateDescriptor,
    model,
    stage: str,
) -> tuple[dict[str, Any], list[ImportIssue]]:
    required_fields = {column["name"] for column in descriptor["required_columns"]}
    field_map = {field.name: field for field in model._meta.fields}
    pk_name = model._meta.pk.name
    normalized_values: dict[str, Any] = {}
    issues: list[ImportIssue] = []

    temp_row = ImportRow(batch=batch, row_number=row_number, edited_values=edited_values, action=ImportRowAction.CREATE)

    for required in required_fields:
        value = edited_values.get(required)
        field = field_map.get(required)
        if value in ("", None) and field is not None and _is_fk_field(field):
            value = edited_values.get(f"{required}_id")
        if value in ("", None):
            issues.append(
                _row_error(
                    batch=batch,
                    row=temp_row,
                    row_number=row_number,
                    code=ImportIssueCode.MISSING_REQUIRED_COLUMN,
                    field_path=required,
                    message=f"Field '{required}' is required.",
                    stage=stage,
                )
            )

    for key, raw_value in edited_values.items():
        normalized_key = key
        field = field_map.get(key)
        if field is None and key.endswith("_id"):
            fk_name = key[:-3]
            fk_field = field_map.get(fk_name)
            if fk_field is not None and _is_fk_field(fk_field):
                field = fk_field
                normalized_key = fk_name
        if field is None:
            normalized_values[normalized_key] = raw_value
            continue
        if field.name == pk_name and raw_value in ("", None):
            normalized_values[normalized_key] = None
            continue
        try:
            coerced_value = _coerce_value(raw_value, field)
            if coerced_value is None and not getattr(field, "null", False):
                raise ValueError(f"Field '{normalized_key}' cannot be empty.")
            normalized_values[normalized_key] = coerced_value
        except (ValueError, TypeError, InvalidOperation):
            issues.append(
                _row_error(
                    batch=batch,
                    row=temp_row,
                    row_number=row_number,
                    code=ImportIssueCode.INVALID_FIELD_VALUE,
                    field_path=normalized_key,
                    message=f"Invalid value for '{normalized_key}'.",
                    stage=stage,
                )
            )

    return normalized_values, issues


def _matching_key_for_row(
    row_values: dict[str, Any], matching_key_fields: list[str], model
) -> tuple[str | None, str, str | None]:
    key_values = [row_values.get(field) for field in matching_key_fields]
    has_all_keys = all(value not in ("", None) for value in key_values)
    if not has_all_keys:
        return None, ImportRowAction.CREATE, None

    matching_key = "|".join(str(value) for value in key_values)
    lookup = {field: row_values.get(field) for field in matching_key_fields}
    pk_name = model._meta.pk.name
    target_id = model.objects.filter(**lookup).values_list(pk_name, flat=True).first()
    if target_id is None:
        return matching_key, ImportRowAction.CREATE, None
    return matching_key, ImportRowAction.UPDATE, str(target_id)


def sync_row_issue_state(batch: ImportBatch) -> None:
    """Recompute row issue counts and statuses from current issues table."""
    for row in batch.rows.all():
        error_count = ImportIssue.objects.filter(
            batch=batch,
            row=row,
            severity=ImportIssueSeverity.ERROR,
        ).count()
        row.issue_count = error_count
        row.status = ImportRowStatus.INVALID if error_count > 0 else ImportRowStatus.VALID
        row.save(update_fields=["issue_count", "status", "updated_at"])


@transaction.atomic
def stage_parsed_rows(
    *,
    batch: ImportBatch,
    parsed_rows: list[dict[str, Any]],
    descriptor: ImportTemplateDescriptor,
) -> list[ImportIssue]:
    """Replace staged rows with parsed rows and generate parse-stage issues."""
    model = apps.get_model(batch.app_label, batch.model_name)
    batch.rows.all().delete()
    batch.issues.all().delete()

    issues_to_create: list[ImportIssue] = []
    for index, payload in enumerate(parsed_rows, start=2):
        row = ImportRow.objects.create(
            batch=batch,
            row_number=index,
            source_values=payload,
            edited_values=payload,
            action=ImportRowAction.CREATE,
            status=ImportRowStatus.VALID,
            issue_count=0,
        )
        normalized_values, row_issues = _validate_row_values(
            batch=batch,
            row_number=index,
            edited_values=payload,
            descriptor=descriptor,
            model=model,
            stage=ImportIssueStage.PARSE,
        )
        matching_key, action, target_record_id = _matching_key_for_row(
            normalized_values,
            descriptor["matching_key_fields"],
            model,
        )
        row.normalized_values = normalized_values
        row.matching_key = matching_key
        row.action = action
        row.target_record_id = target_record_id
        if row_issues:
            row.status = ImportRowStatus.INVALID
            row.issue_count = len(row_issues)
        row.save(
            update_fields=[
                "normalized_values",
                "matching_key",
                "action",
                "target_record_id",
                "status",
                "issue_count",
                "updated_at",
            ]
        )
        for issue in row_issues:
            issue.row = row
            issues_to_create.append(issue)

    if issues_to_create:
        ImportIssue.objects.bulk_create(issues_to_create)
    sync_row_issue_state(batch)
    return list(ImportIssue.objects.filter(batch=batch).order_by("row_number", "created_at"))


@transaction.atomic
def validate_patched_rows(
    *,
    batch: ImportBatch,
    descriptor: ImportTemplateDescriptor,
    row_numbers: list[int],
) -> list[ImportIssue]:
    """Revalidate edited rows and replace edit-stage issues."""
    model = apps.get_model(batch.app_label, batch.model_name)
    rows = list(batch.rows.filter(row_number__in=row_numbers).order_by("row_number"))
    ImportIssue.objects.filter(
        batch=batch,
        row__in=rows,
        stage__in=[ImportIssueStage.EDIT, ImportIssueStage.VALIDATE, ImportIssueStage.SIMULATE],
    ).delete()

    created_issues: list[ImportIssue] = []
    for row in rows:
        normalized_values, row_issues = _validate_row_values(
            batch=batch,
            row_number=row.row_number,
            edited_values=row.edited_values or {},
            descriptor=descriptor,
            model=model,
            stage=ImportIssueStage.EDIT,
        )
        matching_key, action, target_record_id = _matching_key_for_row(
            normalized_values,
            descriptor["matching_key_fields"],
            model,
        )
        row.normalized_values = normalized_values
        row.matching_key = matching_key
        row.action = action
        row.target_record_id = target_record_id
        row.issue_count = len(row_issues)
        row.status = ImportRowStatus.INVALID if row.issue_count else ImportRowStatus.VALID
        row.save(
            update_fields=[
                "normalized_values",
                "matching_key",
                "action",
                "target_record_id",
                "status",
                "issue_count",
                "updated_at",
            ]
        )
        for issue in row_issues:
            issue.row = row
        created_issues.extend(row_issues)

    if created_issues:
        ImportIssue.objects.bulk_create(created_issues)
    sync_row_issue_state(batch)
    return created_issues
