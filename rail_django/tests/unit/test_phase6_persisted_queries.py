"""
Unit tests for persisted query handling.
"""

from hashlib import sha256

import pytest
from django.core.cache import caches
from django.test import override_settings

from rail_django.extensions.persisted_queries import (
    PERSISTED_QUERY_HASH_MISMATCH,
    PERSISTED_QUERY_NOT_FOUND,
    PERSISTED_QUERY_NOT_ALLOWED,
    resolve_persisted_query,
)
from rail_django.testing import override_rail_settings

pytestmark = pytest.mark.unit


def _hash(query: str) -> str:
    return sha256(query.encode("utf-8")).hexdigest()


def test_persisted_query_roundtrip():
    query = "{ ping }"
    sha = _hash(query)

    payload = {
        "query": query,
        "extensions": {"persistedQuery": {"sha256Hash": sha}},
    }

    with override_settings(
        CACHES={
            "persisted": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache"
            }
        }
    ):
        caches["persisted"].clear()
        with override_rail_settings(
            global_settings={
                "persisted_query_settings": {
                    "enabled": True,
                    "cache_alias": "persisted",
                    "allow_unregistered": True,
                }
            }
        ):
            first = resolve_persisted_query(payload, schema_name="test")
            assert not first.has_error()
            assert first.query == query

            second_payload = {
                "extensions": {"persistedQuery": {"sha256Hash": sha}},
            }
            second = resolve_persisted_query(second_payload, schema_name="test")
            assert not second.has_error()
            assert second.query == query


def test_persisted_query_allowlist_blocks_unknown():
    query = "{ ping }"
    sha = _hash(query)
    payload = {
        "query": query,
        "extensions": {"persistedQuery": {"sha256Hash": sha}},
    }

    with override_rail_settings(
        global_settings={
            "persisted_query_settings": {
                "enabled": True,
                "enforce_allowlist": True,
                "allowlist": {"other": "{ other }"},
            }
        }
    ):
        resolution = resolve_persisted_query(payload, schema_name="test")
        assert resolution.has_error()
        assert resolution.error_code == PERSISTED_QUERY_NOT_ALLOWED


def test_persisted_query_allowlist_allows_unregistered_when_enabled():
    query = "{ ping }"
    sha = _hash(query)
    payload = {
        "query": query,
        "extensions": {"persistedQuery": {"sha256Hash": sha}},
    }

    other_sha = _hash("{ other }")

    with override_settings(
        CACHES={
            "persisted": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache"
            }
        }
    ):
        caches["persisted"].clear()
        with override_rail_settings(
            global_settings={
                "persisted_query_settings": {
                    "enabled": True,
                    "cache_alias": "persisted",
                    "allow_unregistered": True,
                    "enforce_allowlist": False,
                    "allowlist": {other_sha: "{ other }"},
                }
            }
        ):
            first = resolve_persisted_query(payload, schema_name="test")
            assert not first.has_error()
            assert first.query == query

            second_payload = {
                "extensions": {"persistedQuery": {"sha256Hash": sha}},
            }
            second = resolve_persisted_query(second_payload, schema_name="test")
            assert not second.has_error()
            assert second.query == query


def test_persisted_query_hash_only_not_found_without_allowlist_enforcement():
    query = "{ ping }"
    sha = _hash(query)
    payload = {"extensions": {"persistedQuery": {"sha256Hash": sha}}}

    other_sha = _hash("{ other }")

    with override_settings(
        CACHES={
            "persisted": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache"
            }
        }
    ):
        caches["persisted"].clear()
        with override_rail_settings(
            global_settings={
                "persisted_query_settings": {
                    "enabled": True,
                    "cache_alias": "persisted",
                    "allow_unregistered": True,
                    "enforce_allowlist": False,
                    "allowlist": {other_sha: "{ other }"},
                }
            }
        ):
            resolution = resolve_persisted_query(payload, schema_name="test")
            assert resolution.has_error()
            assert resolution.error_code == PERSISTED_QUERY_NOT_FOUND


def test_persisted_query_hash_mismatch():
    payload = {
        "query": "{ ping }",
        "extensions": {"persistedQuery": {"sha256Hash": "wrong"}},
    }

    with override_rail_settings(
        global_settings={
            "persisted_query_settings": {"enabled": True}
        }
    ):
        resolution = resolve_persisted_query(payload, schema_name="test")
        assert resolution.has_error()
        assert resolution.error_code == PERSISTED_QUERY_HASH_MISMATCH
