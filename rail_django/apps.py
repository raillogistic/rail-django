import logging

from django.apps import AppConfig
from django.conf import settings
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)


class AppConfig(AppConfig):
    name = "rail_django"
    verbose_name = "Rail Django"

    def ready(self) -> None:
        connection_created.connect(
            _configure_sqlite_connection,
            dispatch_uid="rail_django.sqlite_connection_configuration",
        )
        mode = getattr(settings, "RAIL_METADATA_DEPLOY_VERSION", {}).get(
            "mode", "command"
        )

        if mode == "migration":
            post_migrate.connect(_bump_on_migrate, sender=self)
        elif mode == "startup":
            try:
                from rail_django.extensions.metadata.deploy_version import (
                    bump_deploy_version,
                )

                bump_deploy_version()
                logger.info("Metadata deploy version bumped on startup.")
            except Exception as exc:
                logger.warning(
                    "Failed to bump metadata deploy version on startup: %s", exc
                )


def _bump_on_migrate(**kwargs) -> None:
    try:
        from rail_django.extensions.metadata.deploy_version import bump_deploy_version

        bump_deploy_version()
        logger.info("Metadata deploy version bumped after migrations.")
    except Exception as exc:
        logger.warning("Failed to bump metadata deploy version on migrate: %s", exc)


def _normalize_sqlite_journal_mode(raw_mode: object) -> str | None:
    mode = str(raw_mode or "").strip().upper()
    if not mode:
        return "WAL"
    allowed_modes = {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"}
    if mode in allowed_modes:
        return mode
    logger.warning(
        "Ignoring invalid RAIL_SQLITE_JOURNAL_MODE value '%s'. " "Expected one of: %s",
        raw_mode,
        ", ".join(sorted(allowed_modes)),
    )
    return None


def _resolve_busy_timeout_ms(connection) -> int:
    timeout_from_db_options = (
        (connection.settings_dict or {}).get("OPTIONS", {}) or {}
    ).get("timeout")
    if timeout_from_db_options is not None:
        try:
            return max(int(float(timeout_from_db_options) * 1000), 0)
        except (TypeError, ValueError):
            pass

    raw_setting = getattr(settings, "RAIL_SQLITE_BUSY_TIMEOUT_MS", 20000)
    try:
        return max(int(raw_setting), 0)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid RAIL_SQLITE_BUSY_TIMEOUT_MS value '%s'; defaulting to 20000ms.",
            raw_setting,
        )
        return 20000


def _configure_sqlite_connection(sender, connection, **kwargs) -> None:
    if connection.vendor != "sqlite":
        return

    busy_timeout_ms = _resolve_busy_timeout_ms(connection)
    journal_mode = _normalize_sqlite_journal_mode(
        getattr(settings, "RAIL_SQLITE_JOURNAL_MODE", "WAL")
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
            if journal_mode:
                cursor.execute(f"PRAGMA journal_mode={journal_mode}")
    except Exception as exc:
        logger.warning(
            "Unable to apply SQLite connection tuning (busy_timeout=%sms, journal_mode=%s): %s",
            busy_timeout_ms,
            journal_mode or "unchanged",
            exc,
        )
