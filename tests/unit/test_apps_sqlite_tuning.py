from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import Mock, patch

import pytest
from django.test import override_settings

from rail_django.apps import (
    _prebuild_graphql_schemas_on_startup,
    _configure_sqlite_connection,
    _normalize_sqlite_journal_mode,
    _resolve_busy_timeout_ms,
)

pytestmark = pytest.mark.unit


@dataclass
class _CursorRecorder:
    commands: list[str] = field(default_factory=list)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str) -> None:
        self.commands.append(sql)


@dataclass
class _ConnectionStub:
    vendor: str = "sqlite"
    timeout: float | None = None
    cursor_recorder: _CursorRecorder = field(default_factory=_CursorRecorder)

    @property
    def settings_dict(self) -> dict:
        options = {}
        if self.timeout is not None:
            options["timeout"] = self.timeout
        return {"OPTIONS": options}

    def cursor(self):
        return self.cursor_recorder


def test_normalize_sqlite_journal_mode_defaults_to_wal():
    assert _normalize_sqlite_journal_mode("") == "WAL"
    assert _normalize_sqlite_journal_mode(None) == "WAL"


def test_normalize_sqlite_journal_mode_rejects_invalid_value():
    assert _normalize_sqlite_journal_mode("not-a-mode") is None


def test_resolve_busy_timeout_uses_database_option_timeout():
    connection = _ConnectionStub(timeout=7.5)
    assert _resolve_busy_timeout_ms(connection) == 7500


@override_settings(RAIL_SQLITE_BUSY_TIMEOUT_MS=16000, RAIL_SQLITE_JOURNAL_MODE="WAL")
def test_configure_sqlite_connection_applies_pragmas_for_sqlite():
    connection = _ConnectionStub(vendor="sqlite", timeout=None)

    _configure_sqlite_connection(sender=None, connection=connection)

    assert "PRAGMA busy_timeout=16000" in connection.cursor_recorder.commands
    assert "PRAGMA journal_mode=WAL" in connection.cursor_recorder.commands


@override_settings(RAIL_SQLITE_BUSY_TIMEOUT_MS=16000, RAIL_SQLITE_JOURNAL_MODE="WAL")
def test_configure_sqlite_connection_skips_non_sqlite():
    connection = _ConnectionStub(vendor="postgresql", timeout=None)

    _configure_sqlite_connection(sender=None, connection=connection)

    assert connection.cursor_recorder.commands == []


@override_settings(
    RAIL_DJANGO_GRAPHQL={"schema_settings": {}},
    RAIL_DJANGO_GRAPHQL_SCHEMAS={
        "gql": {"schema_settings": {"prebuild_on_startup": True}},
        "auth": {"schema_settings": {"prebuild_on_startup": False}},
    },
)
def test_prebuild_graphql_schemas_on_startup_builds_opted_in_schemas():
    enabled_schema = Mock(name="enabled_schema")
    enabled_schema.name = "gql"
    disabled_schema = Mock(name="disabled_schema")
    disabled_schema.name = "auth"
    schema_registry = Mock()
    schema_registry._initialized = False
    schema_registry.list_schemas.return_value = [enabled_schema, disabled_schema]

    with (
        patch("rail_django.apps._startup_schema_prebuild_done", False),
        patch("rail_django.core.registry.schema_registry", schema_registry),
        patch("rail_django.core.settings.SchemaSettings") as mock_schema_settings,
    ):
        mock_schema_settings.from_schema.side_effect = [
            Mock(prebuild_on_startup=True),
            Mock(prebuild_on_startup=False),
        ]

        _prebuild_graphql_schemas_on_startup()

    schema_registry.discover_schemas.assert_called_once_with()
    schema_registry.get_schema_instance.assert_called_once_with("gql")


@override_settings(
    RAIL_DJANGO_GRAPHQL={"schema_settings": {}},
    RAIL_DJANGO_GRAPHQL_SCHEMAS={
        "gql": {"schema_settings": {"prebuild_on_startup": False}}
    },
)
def test_prebuild_graphql_schemas_on_startup_skips_when_not_requested():
    schema_registry = Mock()
    schema_registry._initialized = False

    with (
        patch("rail_django.apps._startup_schema_prebuild_done", False),
        patch("rail_django.core.registry.schema_registry", schema_registry),
    ):
        _prebuild_graphql_schemas_on_startup()

    schema_registry.discover_schemas.assert_not_called()
    schema_registry.get_schema_instance.assert_not_called()
