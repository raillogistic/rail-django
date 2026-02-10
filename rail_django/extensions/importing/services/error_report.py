"""Error report generation for import issues."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from django.conf import settings

from ..models import ImportBatch


def _report_directory() -> Path:
    media_root = getattr(settings, "MEDIA_ROOT", "") or tempfile.gettempdir()
    report_dir = Path(media_root) / "import-reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def generate_error_report(batch: ImportBatch) -> str:
    """Generate CSV issue report for a batch and return report path."""
    report_dir = _report_directory()
    file_name = f"import-errors-{batch.id}.csv"
    file_path = report_dir / file_name

    with file_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rowNumber",
                "fieldPath",
                "code",
                "severity",
                "stage",
                "message",
                "suggestedFix",
            ]
        )
        for issue in batch.issues.all().order_by("row_number", "created_at"):
            writer.writerow(
                [
                    issue.row_number or "",
                    issue.field_path or "",
                    issue.code,
                    issue.severity,
                    issue.stage,
                    issue.message,
                    issue.suggested_fix or "",
                ]
            )

    batch.error_report_path = str(file_path)
    batch.save(update_fields=["error_report_path", "updated_at"])
    return str(file_path)

