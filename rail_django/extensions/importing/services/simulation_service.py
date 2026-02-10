"""Dry-run simulation service for import batches."""

from __future__ import annotations

import time

from django.db import transaction

from ..models import (
    ImportBatch,
    ImportBatchStatus,
    ImportIssueSeverity,
    ImportRowAction,
    ImportRowStatus,
    ImportSimulationSnapshot,
)


@transaction.atomic
def run_simulation(batch: ImportBatch) -> dict[str, int | bool]:
    """Compute dry-run summary and persist snapshot without external writes."""
    started = time.perf_counter()
    warning_count = batch.issues.filter(severity=ImportIssueSeverity.WARNING).count()
    blocking_errors = batch.issues.filter(severity=ImportIssueSeverity.ERROR).count()
    would_create = batch.rows.filter(
        action=ImportRowAction.CREATE, status=ImportRowStatus.VALID
    ).count()
    would_update = batch.rows.filter(
        action=ImportRowAction.UPDATE, status=ImportRowStatus.VALID
    ).count()
    can_commit = blocking_errors == 0 and batch.invalid_rows == 0
    duration_ms = int((time.perf_counter() - started) * 1000)

    snapshot = ImportSimulationSnapshot.objects.create(
        batch=batch,
        can_commit=can_commit,
        would_create=would_create,
        would_update=would_update,
        blocking_errors=blocking_errors,
        warnings=warning_count,
        duration_ms=duration_ms,
    )

    batch.status = (
        ImportBatchStatus.SIMULATED if can_commit else ImportBatchStatus.SIMULATION_FAILED
    )
    batch.create_rows = would_create
    batch.update_rows = would_update
    batch.save(update_fields=["status", "create_rows", "update_rows", "updated_at"])

    return {
        "can_commit": snapshot.can_commit,
        "would_create": snapshot.would_create,
        "would_update": snapshot.would_update,
        "blocking_issues": snapshot.blocking_errors,
        "warnings": snapshot.warnings,
        "duration_ms": snapshot.duration_ms,
    }

