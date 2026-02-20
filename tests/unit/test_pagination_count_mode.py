"""
Unit tests for paginated smart-count strategy helpers.
"""

from types import SimpleNamespace

import pytest

from rail_django.generators.queries import pagination


class _StubQuerySet:
    """Minimal queryset stub for count-resolution tests."""

    def __init__(self, count_value: int):
        self._count_value = count_value
        self.count_calls = 0

    def count(self) -> int:
        self.count_calls += 1
        return self._count_value


def test_normalize_count_mode_defaults_to_exact() -> None:
    assert pagination._normalize_count_mode(None) == "exact"
    assert pagination._normalize_count_mode("UNKNOWN") == "exact"


def test_normalize_count_mode_accepts_auto_case_insensitive() -> None:
    assert pagination._normalize_count_mode("auto") == "auto"
    assert pagination._normalize_count_mode("AUTO") == "auto"


def test_query_has_manual_filters_detects_custom_and_where() -> None:
    assert pagination._query_has_manual_filters({"where": {"id": {"eq": 1}}}) is True
    assert pagination._query_has_manual_filters({"status": "OPEN"}) is True
    assert pagination._query_has_manual_filters({"order_by": ["-id"]}) is False


def test_resolve_total_count_uses_exact_for_exact_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    queryset = _StubQuerySet(count_value=42)
    settings = SimpleNamespace(
        enable_estimated_counts=True,
        estimated_count_min_rows=50000,
    )

    monkeypatch.setattr(
        pagination,
        "_can_use_estimated_count",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        pagination,
        "_estimate_queryset_count",
        lambda *_args, **_kwargs: 100_000,
    )

    total_count, is_estimated = pagination._resolve_total_count(
        queryset,
        {},
        count_mode="exact",
        has_property_ordering=False,
        settings=settings,
    )

    assert total_count == 42
    assert is_estimated is False
    assert queryset.count_calls == 1


def test_resolve_total_count_uses_estimate_for_auto_large_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queryset = _StubQuerySet(count_value=42)
    settings = SimpleNamespace(
        enable_estimated_counts=True,
        estimated_count_min_rows=50000,
    )

    monkeypatch.setattr(
        pagination,
        "_can_use_estimated_count",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        pagination,
        "_estimate_queryset_count",
        lambda *_args, **_kwargs: 120_000,
    )

    total_count, is_estimated = pagination._resolve_total_count(
        queryset,
        {},
        count_mode="auto",
        has_property_ordering=False,
        settings=settings,
    )

    assert total_count == 120_000
    assert is_estimated is True
    assert queryset.count_calls == 0


def test_resolve_total_count_falls_back_to_exact_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queryset = _StubQuerySet(count_value=42)
    settings = SimpleNamespace(
        enable_estimated_counts=True,
        estimated_count_min_rows=50000,
    )

    monkeypatch.setattr(
        pagination,
        "_can_use_estimated_count",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        pagination,
        "_estimate_queryset_count",
        lambda *_args, **_kwargs: 1200,
    )

    total_count, is_estimated = pagination._resolve_total_count(
        queryset,
        {},
        count_mode="auto",
        has_property_ordering=False,
        settings=settings,
    )

    assert total_count == 42
    assert is_estimated is False
    assert queryset.count_calls == 1
