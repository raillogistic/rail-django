"""In-memory fixed-window rate limiter."""

from __future__ import annotations

from collections import defaultdict
from time import time

WINDOW_SECONDS = 60
REQUEST_LIMIT = 120
_requests: dict[str, list[float]] = defaultdict(list)


def is_rate_limited(subject: str, limit: int = REQUEST_LIMIT, window: int = WINDOW_SECONDS) -> bool:
    now = time()
    entries = [ts for ts in _requests[subject] if ts > now - window]
    entries.append(now)
    _requests[subject] = entries
    return len(entries) > limit
