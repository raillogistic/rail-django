"""Cache key utilities."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _digest(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:24]


def table_bootstrap_key(app: str, model: str, *, user_scope: str) -> str:
    return f"table:bootstrap:{app}:{model}:{user_scope}"


def table_rows_key(
    app: str,
    model: str,
    *,
    user_scope: str,
    payload: dict[str, Any],
) -> str:
    signature = _digest(payload)
    return f"table:rows:{app}:{model}:{user_scope}:{signature}"
