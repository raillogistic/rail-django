"""Performance metric collection for table APIs."""

from __future__ import annotations

from collections import defaultdict

_metrics: dict[str, list[float]] = defaultdict(list)


def record_metric(name: str, value: float) -> None:
    _metrics[name].append(float(value))


def metric_summary(name: str) -> dict:
    values = _metrics.get(name, [])
    if not values:
        return {"count": 0, "avg": 0.0, "max": 0.0}
    return {
        "count": len(values),
        "avg": sum(values) / len(values),
        "max": max(values),
    }
