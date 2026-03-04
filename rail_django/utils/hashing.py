"""Hashing helpers used for stable, non-reversible identifiers."""

from __future__ import annotations

import hashlib
from typing import Union


def short_hash(value: Union[str, bytes], *, length: int = 12) -> str:
    """
    Return a stable short digest for internal identifiers.

    The function uses SHA-256 and truncates the hexadecimal output. It is
    intended for cache keys, correlation IDs, and internal naming tokens.
    """
    if length <= 0:
        raise ValueError("length must be greater than zero")

    payload = value if isinstance(value, bytes) else str(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:length]


__all__ = ["short_hash"]
