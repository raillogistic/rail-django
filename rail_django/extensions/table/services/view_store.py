"""In-memory table view store."""

from datetime import datetime

_VIEWS: dict[str, dict] = {}


def save_view(app: str, model: str, name: str, config, is_public: bool = False) -> dict:
    key = f"{app}:{model}:{name}"
    now = datetime.utcnow().isoformat()
    payload = {
        "id": key,
        "name": name,
        "isDefault": False,
        "isPublic": bool(is_public),
        "config": config,
        "createdAt": _VIEWS.get(key, {}).get("createdAt", now),
        "updatedAt": now,
    }
    _VIEWS[key] = payload
    return payload

