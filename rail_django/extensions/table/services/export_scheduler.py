"""Simple export scheduler for table v3."""

from datetime import datetime, timedelta

from ..errors.handlers import to_error
from ..errors.taxonomy import TableErrorCode
from ..security.access import get_table_permissions, resolve_table_model


def schedule_export(app: str, model: str, export_format: str | None = None, *, user=None) -> dict:
    model_cls = resolve_table_model(app, model)
    permissions = get_table_permissions(user, model_cls)
    if not permissions.can_export:
        return {
            "ok": False,
            "exportId": None,
            "estimatedCompletionTime": None,
            "notifyOnComplete": False,
            "downloadUrl": None,
            "errors": [to_error(TableErrorCode.PERMISSION, "Export permission required")],
        }

    export_id = f"exp:{app}:{model}:{int(datetime.utcnow().timestamp())}"
    eta = (datetime.utcnow() + timedelta(seconds=5)).isoformat()
    return {
        "ok": True,
        "exportId": export_id,
        "estimatedCompletionTime": eta,
        "notifyOnComplete": True,
        "downloadUrl": f"/exports/{export_id}.{export_format or 'csv'}",
        "errors": [],
    }
