"""Audit logging for table operations."""

from __future__ import annotations

from datetime import datetime


AUDIT_EVENTS: list[dict] = []


def log_audit(action: str, target: str, user_id: str | None = None, metadata: dict | None = None) -> None:
    AUDIT_EVENTS.append(
        {
            "action": action,
            "target": target,
            "userId": user_id,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
    )
