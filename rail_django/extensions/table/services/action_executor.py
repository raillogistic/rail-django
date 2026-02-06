"""Action execution service for table v3."""

from django.apps import apps

from ..errors.handlers import to_error
from ..errors.taxonomy import TableErrorCode
from ..security.audit_logger import log_audit
from ..security.anomaly_detector import detect_action_anomaly
from ..security.input_validator import validate_payload
from ..security.rate_limiter import is_rate_limited


def execute_table_action(input_data: dict) -> dict:
    app = input_data["app"]
    model = input_data["model"]
    action_id = input_data["actionId"]
    row_ids = input_data.get("rowIds") or []
    payload = input_data.get("payload") or {}
    user_id = input_data.get("userId")

    if is_rate_limited(f"{app}:{model}:{user_id or 'anonymous'}"):
        return {
            "ok": False,
            "actionId": action_id,
            "affectedIds": [],
            "errors": [
                to_error(TableErrorCode.RATE_LIMIT, "Rate limit exceeded", retryable=True)
            ],
        }

    validation_errors = validate_payload(payload) if isinstance(payload, dict) else []
    if validation_errors:
        return {
            "ok": False,
            "actionId": action_id,
            "affectedIds": [],
            "errors": [
                to_error(TableErrorCode.VALIDATION, msg) for msg in validation_errors
            ],
        }

    if detect_action_anomaly(action_id, row_ids, payload):
        log_audit(
            "table.anomaly",
            f"{app}.{model}",
            user_id=str(user_id) if user_id else None,
            metadata={"actionId": action_id, "rowCount": len(row_ids)},
        )
        return {
            "ok": False,
            "actionId": action_id,
            "affectedIds": [],
            "errors": [
                to_error(
                    TableErrorCode.PERMISSION,
                    "Anomalous action blocked",
                    retryable=False,
                )
            ],
        }

    model_cls = apps.get_model(app, model)

    if action_id != "delete":
        return {
            "ok": False,
            "actionId": action_id,
            "affectedIds": [],
            "errors": [
                to_error(
                    TableErrorCode.VALIDATION,
                    f"Unsupported action '{action_id}'",
                    retryable=False,
                )
            ],
        }

    qs = model_cls.objects.filter(pk__in=row_ids)
    deleted_ids = [str(value) for value in qs.values_list("pk", flat=True)]
    qs.delete()
    log_audit("table.delete", f"{app}.{model}", user_id=str(user_id) if user_id else None)
    return {"ok": True, "actionId": action_id, "affectedIds": deleted_ids, "errors": []}
