"""
Unit tests for performance metrics collector.
"""

import pytest

from rail_django.extensions.performance_metrics import PerformanceMetricsCollector

pytestmark = pytest.mark.unit


def test_record_query_execution_updates_frequency_and_alerts():
    collector = PerformanceMetricsCollector(
        max_history_size=10, slow_query_threshold=0.5, complex_query_threshold=1
    )

    collector.record_query_execution("query Ping { ping }", 0.2)
    collector.record_query_execution("query Ping { ping }", 0.8)

    assert len(collector.execution_history) == 2
    assert len(collector.query_frequency) == 1
    assert len(collector.slow_query_alerts) == 1

    stats = collector.get_most_frequent_queries(limit=1)[0]
    assert stats.call_count == 2
    assert stats.max_execution_time >= 0.8


def test_execution_time_distribution_reports_min_max_avg():
    collector = PerformanceMetricsCollector(max_history_size=10)
    collector.record_query_execution("query Alpha { alpha }", 0.1)
    collector.record_query_execution("query Beta { beta }", 0.3)
    collector.record_query_execution("query Gamma { gamma }", 0.5)

    distribution = collector.get_execution_time_distribution(time_window_minutes=60)
    assert distribution.total_requests == 3
    assert distribution.min_time == 0.1
    assert distribution.max_time == 0.5
    assert distribution.avg_time > 0


