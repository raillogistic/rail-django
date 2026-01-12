from .framework_settings import *  # noqa: F403

INSTALLED_APPS = list(INSTALLED_APPS) + ["test_app", "tests"]  # noqa: F405

RAIL_DJANGO_GRAPHQL = dict(RAIL_DJANGO_GRAPHQL)  # noqa: F405
_schema_settings = dict(RAIL_DJANGO_GRAPHQL.get("schema_settings", {}))
_schema_settings["auto_camelcase"] = True
RAIL_DJANGO_GRAPHQL["schema_settings"] = _schema_settings

_type_settings = dict(RAIL_DJANGO_GRAPHQL.get("type_generation_settings", {}))
_type_settings["auto_camelcase"] = True
RAIL_DJANGO_GRAPHQL["type_generation_settings"] = _type_settings

MIGRATION_MODULES = {"test_app": None, "tests": None}
