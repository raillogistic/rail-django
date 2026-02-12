"""
Helpers for generated model-form GraphQL contract pagination/normalization.
"""

from __future__ import annotations

from typing import Any

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 200


def coerce_page(page: int | None) -> int:
    return max(int(page or DEFAULT_PAGE), 1)


def coerce_per_page(per_page: int | None) -> int:
    safe = int(per_page or DEFAULT_PER_PAGE)
    return max(min(safe, MAX_PER_PAGE), 1)


def paginate_contract_results(
    items: list[dict[str, Any]],
    *,
    page: int | None = None,
    per_page: int | None = None,
) -> dict[str, Any]:
    safe_page = coerce_page(page)
    safe_per_page = coerce_per_page(per_page)
    start = (safe_page - 1) * safe_per_page
    end = start + safe_per_page
    return {
        "page": safe_page,
        "per_page": safe_per_page,
        "total": len(items),
        "results": items[start:end],
    }
