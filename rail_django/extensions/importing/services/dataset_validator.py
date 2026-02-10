"""Dataset-level validation for duplicate keys and target checks."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.apps import apps
from django.db import transaction

from ..constants import ImportIssueCode
from ..models import (
    ImportBatch,
    ImportBatchStatus,
    ImportIssue,
    ImportIssueSeverity,
    ImportIssueStage,
    ImportRowAction,
)
from ..types import ImportTemplateDescriptor
from .batch_service import recompute_batch_counters
from .row_validator import sync_row_issue_state


def _lookup_payload(row) -> dict[str, Any]:
    if isinstance(row.normalized_values, dict):
        return row.normalized_values
    if isinstance(row.edited_values, dict):
        return row.edited_values
    return {}


@transaction.atomic
def validate_dataset(
    *,
    batch: ImportBatch,
    descriptor: ImportTemplateDescriptor,
) -> list[ImportIssue]:
    """Run dataset-level validations and persist issues."""
    model = apps.get_model(batch.app_label, batch.model_name)
    rows = list(batch.rows.all().order_by("row_number"))
    matching_key_fields = descriptor["matching_key_fields"]

    ImportIssue.objects.filter(batch=batch, stage=ImportIssueStage.VALIDATE).delete()
    new_issues: list[ImportIssue] = []

    duplicates: dict[str, list] = defaultdict(list)
    for row in rows:
        if row.matching_key:
            duplicates[row.matching_key].append(row)

    for matching_key, duplicate_rows in duplicates.items():
        if len(duplicate_rows) < 2:
            continue
        for row in duplicate_rows:
            new_issues.append(
                ImportIssue(
                    batch=batch,
                    row=row,
                    row_number=row.row_number,
                    field_path=",".join(matching_key_fields),
                    code=ImportIssueCode.DUPLICATE_MATCHING_KEY,
                    severity=ImportIssueSeverity.ERROR,
                    message=f"Duplicate matching key '{matching_key}' in batch.",
                    stage=ImportIssueStage.VALIDATE,
                )
            )

    for row in rows:
        payload = _lookup_payload(row)
        lookup = {field: payload.get(field) for field in matching_key_fields}
        has_complete_key = all(value not in ("", None) for value in lookup.values())
        if not has_complete_key:
            next_action = ImportRowAction.CREATE
            target_record_id = None
        else:
            pk_name = model._meta.pk.name
            existing_target = model.objects.filter(**lookup).values_list(pk_name, flat=True).first()
            if existing_target is None:
                # Upsert behavior: keep row creatable when matching key has no target.
                next_action = ImportRowAction.CREATE
                target_record_id = None
            else:
                next_action = ImportRowAction.UPDATE
                target_record_id = str(existing_target)

        if row.action != next_action or row.target_record_id != target_record_id:
            row.action = next_action
            row.target_record_id = target_record_id
            row.save(update_fields=["action", "target_record_id", "updated_at"])

    if new_issues:
        ImportIssue.objects.bulk_create(new_issues)

    sync_row_issue_state(batch)
    recompute_batch_counters(batch)
    batch.status = (
        ImportBatchStatus.VALIDATION_FAILED if batch.invalid_rows > 0 else ImportBatchStatus.VALIDATED
    )
    batch.save(update_fields=["status", "updated_at"])

    return list(
        ImportIssue.objects.filter(batch=batch, stage=ImportIssueStage.VALIDATE).order_by(
            "row_number", "created_at"
        )
    )
