"""Batch persistence service for import lifecycle storage."""

from __future__ import annotations

from collections.abc import Iterable
from django.db import transaction
from django.db.models import Count, Q

from ..models import ImportBatch, ImportBatchStatus, ImportRow, ImportRowStatus
from ..types import ImportRowPatch


def create_import_batch(
    *,
    app_label: str,
    model_name: str,
    template_id: str,
    template_version: str,
    uploaded_by_user_id: str,
    file_name: str,
    file_format: str,
) -> ImportBatch:
    return ImportBatch.objects.create(
        app_label=app_label,
        model_name=model_name,
        template_id=template_id,
        template_version=template_version,
        uploaded_by_user_id=uploaded_by_user_id,
        file_name=file_name,
        file_format=file_format,
        status=ImportBatchStatus.UPLOADED,
    )


def get_import_batch(batch_id: str) -> ImportBatch | None:
    return (
        ImportBatch.objects.select_related()
        .prefetch_related("rows", "issues", "simulation_snapshots")
        .filter(id=batch_id)
        .first()
    )


def list_import_batches(
    *,
    page: int = 1,
    per_page: int = 50,
    app_label: str | None = None,
    model_name: str | None = None,
    status: str | None = None,
) -> tuple[int, list[ImportBatch]]:
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, 200))

    queryset = ImportBatch.objects.only(
        "id",
        "app_label",
        "model_name",
        "template_id",
        "template_version",
        "status",
        "total_rows",
        "valid_rows",
        "invalid_rows",
        "create_rows",
        "update_rows",
        "committed_rows",
        "created_at",
        "updated_at",
        "submitted_at",
        "committed_at",
    ).order_by("-updated_at", "-created_at")
    if app_label:
        queryset = queryset.filter(app_label=app_label)
    if model_name:
        queryset = queryset.filter(model_name=model_name)
    if status:
        queryset = queryset.filter(status=status)

    total = queryset.count()
    start = max(0, (safe_page - 1) * safe_per_page)
    end = start + safe_per_page
    return total, list(queryset[start:end])


@transaction.atomic
def patch_import_rows(batch: ImportBatch, patches: Iterable[ImportRowPatch]) -> list[ImportRow]:
    touched_rows: list[ImportRow] = []
    for patch in patches:
        row = (
            ImportRow.objects.select_for_update()
            .filter(batch=batch, row_number=patch["row_number"])
            .first()
        )
        if row is None:
            continue
        row.edited_values = patch["edited_values"]
        row.save(update_fields=["edited_values", "updated_at"])
        touched_rows.append(row)

    if touched_rows:
        batch.status = ImportBatchStatus.REVIEWING
        batch.save(update_fields=["status", "updated_at"])

    return touched_rows


def recompute_batch_counters(batch: ImportBatch) -> ImportBatch:
    counters = ImportRow.objects.filter(batch=batch).aggregate(
        total_rows=Count("id"),
        valid_rows=Count("id", filter=Q(status=ImportRowStatus.VALID)),
        invalid_rows=Count("id", filter=Q(status=ImportRowStatus.INVALID)),
        create_rows=Count("id", filter=Q(action="CREATE")),
        update_rows=Count("id", filter=Q(action="UPDATE")),
    )

    batch.total_rows = counters["total_rows"] or 0
    batch.valid_rows = counters["valid_rows"] or 0
    batch.invalid_rows = counters["invalid_rows"] or 0
    batch.create_rows = counters["create_rows"] or 0
    batch.update_rows = counters["update_rows"] or 0
    batch.save(
        update_fields=[
            "total_rows",
            "valid_rows",
            "invalid_rows",
            "create_rows",
            "update_rows",
            "updated_at",
        ]
    )
    return batch
