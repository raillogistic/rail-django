"""
Unit tests for JSON-based GraphQLMeta configuration loading.
"""

import json
from types import SimpleNamespace

import pytest

from rail_django.core.meta import get_model_graphql_meta
from rail_django.core.meta_json import clear_meta_configs, load_app_meta_configs
from rail_django.security.rbac import role_manager
from test_app.models import Category

pytestmark = pytest.mark.unit


def filter_by_name(queryset, name, value):
    return queryset


def resolve_custom_list(queryset, info, **kwargs):
    return queryset


def allow_all(user=None, operation=None, info=None, instance=None, model=None):
    return True


def test_meta_json_applies_to_models(tmp_path):
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "roles": {
                    "meta_role": {
                        "description": "Meta role",
                        "role_type": "business",
                        "permissions": ["project.read"],
                    }
                },
                "models": {
                    "Category": {
                        "fields": {"exclude": ["description"]},
                        "filtering": {
                            "quick": ["name"],
                            "custom": {
                                "by_name": "rail_django.tests.unit.test_meta_json.filter_by_name"
                            },
                        },
                        "resolvers": {
                            "queries": {
                                "custom_list": "rail_django.tests.unit.test_meta_json.resolve_custom_list"
                            }
                        },
                        "access": {
                            "operations": {
                                "list": {
                                    "condition": "rail_django.tests.unit.test_meta_json.allow_all"
                                }
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    clear_meta_configs()
    if hasattr(Category, "_graphql_meta_instance"):
        delattr(Category, "_graphql_meta_instance")

    load_app_meta_configs([SimpleNamespace(path=str(tmp_path), label="test_app")])
    graphql_meta = get_model_graphql_meta(Category)

    assert role_manager.get_role_definition("meta_role") is not None
    assert graphql_meta.field_config.exclude == ["description"]
    assert "name" in graphql_meta.filtering.quick
    assert callable(graphql_meta.filtering.custom["by_name"])
    assert callable(graphql_meta.resolvers.queries["custom_list"])
    assert callable(graphql_meta.access_config.operations["list"].condition)

    clear_meta_configs()
    role_manager._roles_cache.pop("meta_role", None)
    role_manager._role_hierarchy.pop("meta_role", None)
    if hasattr(Category, "_graphql_meta_instance"):
        delattr(Category, "_graphql_meta_instance")
