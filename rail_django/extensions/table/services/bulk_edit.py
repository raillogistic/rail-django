"""Bulk edit service."""

from django.apps import apps


def preview_bulk_edit(app: str, model: str, row_ids: list, changes: dict) -> dict:
    model_cls = apps.get_model(app, model)
    qs = model_cls.objects.filter(pk__in=row_ids)
    previews = []
    for row in qs:
        for field, new_value in changes.items():
            previews.append(
                {
                    "rowId": str(row.pk),
                    "field": field,
                    "oldValue": str(getattr(row, field, "")),
                    "newValue": str(new_value),
                    "warnings": [],
                }
            )
    return {"ok": True, "affectedCount": len(previews), "previewChanges": previews, "errors": []}


def apply_bulk_edit(app: str, model: str, row_ids: list, changes: dict) -> dict:
    model_cls = apps.get_model(app, model)
    qs = model_cls.objects.filter(pk__in=row_ids)
    count = 0
    for row in qs:
        for field, new_value in changes.items():
            setattr(row, field, new_value)
        row.save()
        count += 1
    return {"ok": True, "affectedCount": count, "previewChanges": [], "errors": []}

