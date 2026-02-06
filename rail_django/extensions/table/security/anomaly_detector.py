"""Basic anomaly detection for table actions."""


def detect_action_anomaly(action_id: str, row_ids: list, payload: dict) -> bool:
    if len(row_ids) > 1000:
        return True
    if action_id == "delete" and len(row_ids) > 250:
        return True
    if len(str(payload)) > 100_000:
        return True
    return False
