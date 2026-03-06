"""Bulk edit service."""

from ..errors.handlers import to_error
from ..errors.taxonomy import TableErrorCode
from ..security.access import (
    get_table_permissions,
    get_writable_table_fields,
    resolve_table_model,
    table_mutations_enabled,
)


def preview_bulk_edit(app: str, model: str, row_ids: list, changes: dict, *, user=None) -> dict:
    model_cls = resolve_table_model(app, model)
    qs = model_cls.objects.filter(pk__in=row_ids)
    writable_fields = get_writable_table_fields(user, model_cls)
    previews = []
    for row in qs:
        for field, new_value in changes.items():
            if field not in writable_fields:
                continue
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


def apply_bulk_edit(app: str, model: str, row_ids: list, changes: dict, *, user=None) -> dict:
    if not table_mutations_enabled():
        return {
            "ok": False,
            "affectedCount": 0,
            "previewChanges": [],
            "errors": [to_error(TableErrorCode.PERMISSION, "Table mutations are disabled")],
        }

    model_cls = resolve_table_model(app, model)
    permissions = get_table_permissions(user, model_cls)
    if not permissions.can_update:
        return {
            "ok": False,
            "affectedCount": 0,
            "previewChanges": [],
            "errors": [to_error(TableErrorCode.PERMISSION, "Update permission required")],
        }

    writable_fields = get_writable_table_fields(user, model_cls)
    valid_changes = {
        field: value
        for field, value in (changes or {}).items()
        if field in writable_fields
    }
    if not valid_changes:
        return {
            "ok": False,
            "affectedCount": 0,
            "previewChanges": [],
            "errors": [to_error(TableErrorCode.VALIDATION, "No writable fields were provided")],
        }

    qs = model_cls.objects.filter(pk__in=row_ids)
    count = 0
    for row in qs:
        for field, new_value in valid_changes.items():
            setattr(row, field, new_value)
        row.save(update_fields=list(valid_changes))
        count += 1
    return {"ok": True, "affectedCount": count, "previewChanges": [], "errors": []}
