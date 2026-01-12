"""
Unit tests for Phase 4 performance enhancements.
"""

import graphene
import pytest

from rail_django.core.services import set_query_cache_factory
from rail_django.extensions.optimization import invalidate_query_cache, optimize_query
from rail_django.extensions.query_cache import InMemoryQueryCacheBackend
from rail_django.middleware.performance import QueryMetricsCollector
from rail_django.testing import RailGraphQLTestClient

pytestmark = pytest.mark.unit


class _UserStub:
    def __init__(self, user_id: int):
        self.id = user_id
        self.is_authenticated = True


def test_query_cache_hits_and_invalidation():
    backend = InMemoryQueryCacheBackend()
    set_query_cache_factory(lambda schema_name=None: backend)
    call_counter = {"count": 0}

    class Query(graphene.ObjectType):
        value = graphene.String()

        @optimize_query(enable_caching=True)
        def resolve_value(root, info):
            call_counter["count"] += 1
            return f"value-{call_counter['count']}"

    try:
        schema = graphene.Schema(query=Query)
        client = RailGraphQLTestClient(schema, schema_name="cache")

        first = client.execute("{ value }")
        second = client.execute("{ value }")

        assert first["data"]["value"] == "value-1"
        assert second["data"]["value"] == "value-1"
        assert call_counter["count"] == 1

        invalidate_query_cache(schema_name="cache")
        third = client.execute("{ value }")
        assert third["data"]["value"] == "value-2"
        assert call_counter["count"] == 2
    finally:
        set_query_cache_factory(None)


def test_query_cache_user_specific():
    backend = InMemoryQueryCacheBackend()
    set_query_cache_factory(lambda schema_name=None: backend)
    call_counter = {"count": 0}

    class Query(graphene.ObjectType):
        value = graphene.String()

        @optimize_query(enable_caching=True, user_specific_cache=True)
        def resolve_value(root, info):
            call_counter["count"] += 1
            return f"value-{call_counter['count']}"

    try:
        schema = graphene.Schema(query=Query)
        client = RailGraphQLTestClient(schema, schema_name="cache-user")

        user_a = _UserStub(1)
        user_b = _UserStub(2)

        first = client.execute("{ value }", user=user_a)
        second = client.execute("{ value }", user=user_a)
        third = client.execute("{ value }", user=user_b)

        assert first["data"]["value"] == "value-1"
        assert second["data"]["value"] == "value-1"
        assert third["data"]["value"] == "value-2"
        assert call_counter["count"] == 2
    finally:
        set_query_cache_factory(None)


def test_query_metrics_collector_flags_repeated_queries():
    collector = QueryMetricsCollector(n_plus_one_threshold=2)

    def execute(sql, params, many, context):
        return "ok"

    collector.execute_wrapper(execute, "SELECT 1", None, None, None)
    collector.execute_wrapper(execute, "SELECT 1", None, None, None)
    collector.execute_wrapper(execute, "SELECT 1", None, None, None)

    candidates = collector.get_n_plus_one_candidates()
    assert len(candidates) == 1
    assert candidates[0]["count"] == 3
