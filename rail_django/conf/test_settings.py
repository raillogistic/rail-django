import json

from django.db.backends.signals import connection_created

from .framework_settings import *  # noqa: F403

INSTALLED_APPS = list(INSTALLED_APPS) + ["test_app", "tests"]  # noqa: F405
ROOT_URLCONF = "rail_django.urls"
ENVIRONMENT = "testing"
GRAPHQL_SCHEMA_API_AUTH_REQUIRED = False

RAIL_DJANGO_GRAPHQL = dict(RAIL_DJANGO_GRAPHQL)  # noqa: F405
_schema_settings = dict(RAIL_DJANGO_GRAPHQL.get("schema_settings", {}))
_schema_settings["auto_camelcase"] = True
RAIL_DJANGO_GRAPHQL["schema_settings"] = _schema_settings

_type_settings = dict(RAIL_DJANGO_GRAPHQL.get("type_generation_settings", {}))
_type_settings["auto_camelcase"] = True
RAIL_DJANGO_GRAPHQL["type_generation_settings"] = _type_settings

MIGRATION_MODULES = {"test_app": None, "tests": None}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}


def _sqlite_json_valid(value):
    if value is None:
        return 0
    try:
        json.loads(value)
        return 1
    except (TypeError, ValueError):
        return 0


def _sqlite_json(value):
    if value is None:
        return None
    try:
        json.loads(value)
        return value
    except (TypeError, ValueError):
        return None


def _register_sqlite_functions(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    connection.connection.create_function("JSON", 1, _sqlite_json)
    connection.connection.create_function("JSON_VALID", 1, _sqlite_json_valid)


connection_created.connect(_register_sqlite_functions)
