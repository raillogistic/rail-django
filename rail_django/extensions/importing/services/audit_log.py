"""Audit logging helpers for import lifecycle events."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def log_import_event(
    event_name: str,
    *,
    user_id: str | None = None,
    batch_id: str | None = None,
    details: dict[str, Any] | None = None,
    kpis: dict[str, Any] | None = None,
) -> None:
    payload = {
        "event": event_name,
        "user_id": user_id,
        "batch_id": batch_id,
        "details": details or {},
        "kpis": kpis or {},
    }
    logger.info("import_event=%s", payload)
