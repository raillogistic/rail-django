import pytest

from rail_django.debugging.query_analyzer import (
    ProductionQueryProfiler,
    QueryProfileInput,
)

pytestmark = pytest.mark.unit


def test_profiler_aggregates_n_plus_one_risk_signals():
    profiler = ProductionQueryProfiler()

    report = profiler.profile(
        [
            QueryProfileInput(
                query="{ users { username } }",
                operation_name="UserList",
                count=3,
            ),
            QueryProfileInput(
                query="{ users { users { id } } }",
                operation_name="NestedUsers",
                count=2,
            ),
        ]
    )

    assert report.total_queries == 2
    assert report.total_observations == 5
    assert report.n_plus_one_risk_count == 1
    assert report.entries[1].has_n_plus_one_risk is True
    assert report.to_dict()["entries"][1]["n_plus_one_risk"] is True


def test_profiler_accepts_dictionary_samples():
    report = ProductionQueryProfiler().profile(
        [
            {
                "query": "{ users { username } }",
                "operationName": "UserList",
                "source": "graphql.log",
                "occurrences": "4",
                "durationMs": "21.5",
            }
        ]
    )

    entry = report.entries[0]
    assert entry.operation_name == "UserList"
    assert entry.source == "graphql.log"
    assert entry.count == 4
    assert entry.duration_ms == 21.5
