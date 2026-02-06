"""Simple export scheduler for table v3."""

from datetime import datetime, timedelta


def schedule_export(app: str, model: str, export_format: str | None = None) -> dict:
    export_id = f"exp:{app}:{model}:{int(datetime.utcnow().timestamp())}"
    eta = (datetime.utcnow() + timedelta(seconds=5)).isoformat()
    return {
        "ok": True,
        "exportId": export_id,
        "estimatedCompletionTime": eta,
        "notifyOnComplete": True,
        "downloadUrl": f"/exports/{export_id}.{export_format or 'csv'}",
    }

