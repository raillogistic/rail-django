"""In-memory subscription and presence tracking."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

_subscriptions: dict[str, set[str]] = defaultdict(set)
_presence: dict[str, dict[str, str]] = defaultdict(dict)
_emission_timestamps: dict[str, float] = {}


def _table_key(app: str, model: str) -> str:
    return f"{app}.{model}"


def subscribe(app: str, model: str, user_id: str) -> None:
    _subscriptions[_table_key(app, model)].add(user_id)


def unsubscribe(app: str, model: str, user_id: str) -> None:
    _subscriptions[_table_key(app, model)].discard(user_id)


def set_presence(app: str, model: str, user_id: str, action: str) -> dict:
    payload = {
        "userId": str(user_id),
        "action": action,
        "timestamp": datetime.utcnow().isoformat(),
    }
    _presence[_table_key(app, model)][str(user_id)] = payload
    return payload


def list_presence(app: str, model: str) -> list[dict]:
    return list(_presence[_table_key(app, model)].values())


def can_emit(app: str, model: str, min_interval_seconds: float = 0.5) -> bool:
    from time import time

    key = _table_key(app, model)
    now = time()
    previous = _emission_timestamps.get(key, 0.0)
    if now - previous < min_interval_seconds:
        return False
    _emission_timestamps[key] = now
    return True


def subscription_health(app: str, model: str) -> dict:
    key = _table_key(app, model)
    return {
        "table": key,
        "activeSubscribers": len(_subscriptions.get(key, set())),
        "activePresenceUsers": len(_presence.get(key, {})),
    }
