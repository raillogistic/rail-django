"""
Collectors for query metrics.
"""

import time
from typing import Any


class QueryMetricsCollector:
    """Collect query count/time and spot repeated query patterns."""

    def __init__(self, n_plus_one_threshold: int = 5, max_sql_length: int = 200):
        self.query_count = 0
        self.total_time = 0.0
        self.n_plus_one_threshold = n_plus_one_threshold
        self.max_sql_length = max_sql_length
        self._fingerprints: dict[str, dict[str, Any]] = {}

    def execute_wrapper(self, execute, sql, params, many, context):
        start = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            duration = time.perf_counter() - start
            self.query_count += 1
            self.total_time += duration
            fingerprint = self._normalize_sql(sql)
            data = self._fingerprints.setdefault(
                fingerprint, {"count": 0, "total_time": 0.0}
            )
            data["count"] += 1
            data["total_time"] += duration

    def get_n_plus_one_candidates(self, limit: int = 5) -> list[dict[str, Any]]:
        candidates = [
            {"sql": self._truncate_sql(sql), "count": data["count"]}
            for sql, data in self._fingerprints.items()
            if data["count"] >= self.n_plus_one_threshold
        ]
        candidates.sort(key=lambda item: item["count"], reverse=True)
        return candidates[:limit]

    def _normalize_sql(self, sql: Any) -> str:
        return " ".join(str(sql or "").split())

    def _truncate_sql(self, sql: str) -> str:
        if len(sql) <= self.max_sql_length:
            return sql
        return f"{sql[: self.max_sql_length]}..."
