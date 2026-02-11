"""Atomic commit service for create/update apply operations."""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from ..constants import ImportIssueCode
from ..models import (
    ImportBatch,
    ImportBatchStatus,
    ImportIssue,
    ImportIssueSeverity,
    ImportIssueStage,
    ImportRowAction,
    ImportRowStatus,
)
from ..types import ImportTemplateDescriptor
from .errors import ImportServiceError


def _lookup_payload(row) -> dict[str, Any]:
    if isinstance(row.normalized_values, dict):
        return row.normalized_values
    if isinstance(row.edited_values, dict):
        return row.edited_values
    return {}


def _editable_fields(model) -> set[str]:
    return {
        field.name
        for field in model._meta.fields
        if getattr(field, "editable", True) and not getattr(field, "auto_created", False)
    }


def _is_fk_field(field: Any) -> bool:
    return bool(
        getattr(field, "is_relation", False)
        and getattr(field, "many_to_one", False)
        and not getattr(field, "many_to_many", False)
    )


def _normalize_non_null_value_for_commit(
    *,
    field: Any,
    value: Any,
    action: str,
    field_name: str,
    row_number: int,
) -> tuple[bool, Any]:
    """
    Return `(skip_assignment, normalized_value)` for commit assignment safety.

    - CREATE + None on non-null field with default: skip assignment so DB/model default applies.
    - UPDATE + None on non-null field: skip assignment to preserve existing value.
    - Non-null field without default on CREATE and None: raise validation-like import error.
    """
    if value is not None:
        return False, value
    if getattr(field, "null", False):
        return False, value
    if action == ImportRowAction.CREATE and field.has_default():
        return True, None
    if action == ImportRowAction.UPDATE:
        return True, None
    raise ImportServiceError(
        ImportIssueCode.INVALID_FIELD_VALUE,
        f"Field '{field_name}' cannot be empty.",
        row_number=row_number,
        field_path=field_name,
    )


@transaction.atomic
def commit_batch(
    *,
    batch: ImportBatch,
    descriptor: ImportTemplateDescriptor,
) -> dict[str, int]:
    """Commit valid rows atomically. Any failure aborts all writes."""
    if batch.invalid_rows > 0:
        raise ImportServiceError(
            ImportIssueCode.UNKNOWN_ERROR,
            "Batch still contains invalid rows.",
        )

    model = apps.get_model(batch.app_label, batch.model_name)
    matching_key_fields = descriptor["matching_key_fields"]
    editable = _editable_fields(model)
    model_fields = {field.name: field for field in model._meta.fields}
    pk_name = model._meta.pk.name

    valid_rows = list(batch.rows.filter(status=ImportRowStatus.VALID).order_by("row_number"))
    create_count = 0
    update_count = 0

    try:
        for row in valid_rows:
            payload = _lookup_payload(row)
            if row.action == ImportRowAction.UPDATE:
                lookup = {field: payload.get(field) for field in matching_key_fields}
                if any(value in ("", None) for value in lookup.values()):
                    raise ImportServiceError(
                        ImportIssueCode.RECORD_NOT_FOUND,
                        "Missing update matching key values.",
                        row_number=row.row_number,
                    )
                instance = model.objects.filter(**lookup).first()
                if instance is None:
                    raise ImportServiceError(
                        ImportIssueCode.RECORD_NOT_FOUND,
                        "No existing record matches update key.",
                        row_number=row.row_number,
                    )
                update_fields: list[str] = []
                for field_name, value in payload.items():
                    if field_name not in editable:
                        continue
                    if field_name == pk_name:
                        continue
                    field = model_fields.get(field_name)
                    if field is not None:
                        skip_assignment, normalized_value = _normalize_non_null_value_for_commit(
                            field=field,
                            value=value,
                            action=row.action,
                            field_name=field_name,
                            row_number=row.row_number,
                        )
                        if skip_assignment:
                            continue
                    else:
                        normalized_value = value
                    if field is not None and _is_fk_field(field):
                        setattr(instance, field.attname, normalized_value)
                        update_fields.append(field.attname)
                    else:
                        setattr(instance, field_name, normalized_value)
                        update_fields.append(field_name)
                if update_fields:
                    instance.save(update_fields=sorted(set(update_fields)))
                update_count += 1
            else:
                create_payload: dict[str, Any] = {}
                for field_name, value in payload.items():
                    if field_name not in editable or field_name == pk_name:
                        continue
                    field = model_fields.get(field_name)
                    if field is not None:
                        skip_assignment, normalized_value = _normalize_non_null_value_for_commit(
                            field=field,
                            value=value,
                            action=row.action,
                            field_name=field_name,
                            row_number=row.row_number,
                        )
                        if skip_assignment:
                            continue
                    else:
                        normalized_value = value
                    if field is not None and _is_fk_field(field):
                        create_payload[field.attname] = normalized_value
                    else:
                        create_payload[field_name] = normalized_value
                model.objects.create(**create_payload)
                create_count += 1
    except Exception as exc:
        if isinstance(exc, ImportServiceError):
            raise
        raise ImportServiceError(
            ImportIssueCode.UNKNOWN_ERROR,
            f"Commit failed: {exc}",
        ) from exc

    batch.rows.filter(id__in=[row.id for row in valid_rows]).update(status=ImportRowStatus.COMMITTED)
    committed_rows = create_count + update_count
    batch.status = ImportBatchStatus.COMMITTED
    batch.committed_rows = committed_rows
    batch.create_rows = create_count
    batch.update_rows = update_count
    batch.committed_at = timezone.now()
    batch.submitted_at = timezone.now()
    batch.save(
        update_fields=[
            "status",
            "committed_rows",
            "create_rows",
            "update_rows",
            "committed_at",
            "submitted_at",
            "updated_at",
        ]
    )

    ImportIssue.objects.filter(batch=batch, stage=ImportIssueStage.COMMIT).delete()
    return {
        "total_rows": batch.total_rows,
        "committed_rows": committed_rows,
        "create_rows": create_count,
        "update_rows": update_count,
        "skipped_rows": max(0, batch.total_rows - committed_rows),
    }
