from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from django.test import override_settings

from rail_django.apps import (
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
