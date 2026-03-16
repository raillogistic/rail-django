import logging

from django.apps import AppConfig
from django.conf import settings
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)
_startup_schema_prebuild_done = False


class AppConfig(AppConfig):
    name = "rail_django"
    verbose_name = "Rail Django"

    def ready(self) -> None:
        connection_created.connect(
            _configure_sqlite_connection,
            dispatch_uid="rail_django.sqlite_connection_configuration",
        )
        if getattr(settings, "RAIL_DJANGO_DISCOVER_SCHEMAS_ON_STARTUP", False):
            try:
                from rail_django.core.registry import schema_registry

                schema_registry.discover_schemas()
            except Exception as exc:
                logger.debug("Deferred schema discovery at startup: %s", exc)
        _prebuild_graphql_schemas_on_startup()
        mode = getattr(settings, "RAIL_METADATA_DEPLOY_VERSION", {}).get(
            "mode", "command"
        )

        if mode == "migration":
            post_migrate.connect(
                _bump_on_migrate,
                sender=self,
                dispatch_uid="rail_django.metadata_deploy_version_on_migrate",
            )
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


def _startup_prebuild_requested() -> bool:
    global_config = getattr(settings, "RAIL_DJANGO_GRAPHQL", {}) or {}
    global_schema_settings = global_config.get("schema_settings", {}) or {}
    if bool(global_schema_settings.get("prebuild_on_startup")):
        return True

    schema_configs = getattr(settings, "RAIL_DJANGO_GRAPHQL_SCHEMAS", {}) or {}
    if not isinstance(schema_configs, dict):
        return False

    for config in schema_configs.values():
        if not isinstance(config, dict):
            continue
        if bool(config.get("prebuild_on_startup")):
            return True
        schema_settings = config.get("schema_settings", {}) or {}
        if bool(schema_settings.get("prebuild_on_startup")):
            return True
    return False


def _prebuild_graphql_schemas_on_startup() -> None:
    global _startup_schema_prebuild_done
    if _startup_schema_prebuild_done:
        return

    try:
        from rail_django.core.registry import schema_registry
        from rail_django.core.settings import SchemaSettings
    except Exception as exc:
        logger.debug("Skipping schema prebuild startup hook: %s", exc)
        return

    if not getattr(schema_registry, "_initialized", False):
        if not _startup_prebuild_requested():
            return
        try:
            schema_registry.discover_schemas()
        except Exception as exc:
            logger.debug("Deferred schema prebuild discovery at startup: %s", exc)
            return

    _startup_schema_prebuild_done = True
    prebuilt = 0
    for schema_info in schema_registry.list_schemas(enabled_only=True):
        schema_name = getattr(schema_info, "name", "")
        if not schema_name:
            continue
        try:
            if not SchemaSettings.from_schema(schema_name).prebuild_on_startup:
                continue
            schema_registry.get_schema_instance(schema_name)
            prebuilt += 1
        except Exception as exc:
            logger.debug(
                "Deferred schema prebuild for '%s' at startup: %s",
                schema_name,
                exc,
            )

    if prebuilt:
        logger.info("Prebuilt %s GraphQL schema(s) on startup.", prebuilt)


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
