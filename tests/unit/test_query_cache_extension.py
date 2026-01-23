"""
Unit tests for query cache backend helpers.
"""

import pytest
from unittest.mock import patch

from rail_django.extensions.query_cache import InMemoryQueryCacheBackend

pytestmark = pytest.mark.unit


def test_in_memory_cache_expires_entries():
    backend = InMemoryQueryCacheBackend(default_timeout=5)
    with patch("rail_django.extensions.query_cache.time.time") as now:
        now.return_value = 1000.0
        backend.set("alpha", "value")
        assert backend.get("alpha") == "value"

        now.return_value = 1007.0
        assert backend.get("alpha") is None


def test_in_memory_cache_versions_bump():
    backend = InMemoryQueryCacheBackend()
    first = backend.get_version("schema")
    second = backend.get_version("schema")
    assert first == second

    bumped = backend.bump_version("schema")
    assert bumped != first
    assert backend.get_version("schema") == bumped


