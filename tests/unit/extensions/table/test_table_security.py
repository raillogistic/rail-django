from types import SimpleNamespace

import pytest
from graphql import GraphQLError

from rail_django.extensions.table.cache.keys import table_rows_key
from rail_django.extensions.table.security import access
from rail_django.extensions.table.schema.mutations import TableMutations
from rail_django.extensions.table.services import action_executor, data_resolver

pytestmark = [pytest.mark.unit]


def test_table_rows_cache_key_varies_by_user_and_payload():
    key_a = table_rows_key(
        "inventory",
        "Product",
        user_scope="user:1",
        payload={"page": 1, "ordering": ["-id"]},
    )
    key_b = table_rows_key(
        "inventory",
        "Product",
        user_scope="user:2",
        payload={"page": 1, "ordering": ["-id"]},
    )
    key_c = table_rows_key(
        "inventory",
        "Product",
        user_scope="user:1",
        payload={"page": 2, "ordering": ["-id"]},
    )

    assert key_a != key_b
    assert key_a != key_c


def test_save_table_view_requires_authenticated_user(monkeypatch):
    monkeypatch.setattr(
        "rail_django.extensions.table.schema.mutations.table_mutations_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.schema.mutations.resolve_table_model",
        lambda app, model: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.schema.mutations.get_table_permissions",
        lambda user, model_cls: SimpleNamespace(can_view=True),
    )

    info = SimpleNamespace(context=SimpleNamespace(user=SimpleNamespace(is_authenticated=False)))

    with pytest.raises(GraphQLError, match="Authentication required"):
        TableMutations().resolve_saveTableView(
            info,
            {"app": "inventory", "model": "Product", "name": "default"},
        )


def test_table_rows_requires_view_permission(monkeypatch):
    monkeypatch.setattr(
        data_resolver,
        "resolve_table_model",
        lambda app, model: SimpleNamespace(),
    )
    monkeypatch.setattr(
        data_resolver,
        "get_table_permissions",
        lambda user, model_cls: SimpleNamespace(can_view=False),
    )

    info = SimpleNamespace(context=SimpleNamespace(user=None))

    with pytest.raises(GraphQLError, match="Permission denied"):
        data_resolver.resolve_table_rows(
            {"app": "inventory", "model": "Product"},
            info=info,
        )


def test_execute_table_action_requires_delete_permission(monkeypatch):
    monkeypatch.setattr(action_executor, "table_mutations_enabled", lambda: True)
    monkeypatch.setattr(action_executor, "is_rate_limited", lambda key: False)
    monkeypatch.setattr(action_executor, "validate_payload", lambda payload: [])
    monkeypatch.setattr(
        action_executor,
        "detect_action_anomaly",
        lambda action_id, row_ids, payload: False,
    )
    monkeypatch.setattr(
        action_executor,
        "resolve_table_model",
        lambda app, model: SimpleNamespace(),
    )
    monkeypatch.setattr(
        action_executor,
        "get_table_permissions",
        lambda user, model_cls: SimpleNamespace(can_delete=False),
    )

    result = action_executor.execute_table_action(
        {
            "app": "inventory",
            "model": "Product",
            "actionId": "delete",
            "rowIds": ["1"],
        },
        user=SimpleNamespace(is_authenticated=True),
    )

    assert result["ok"] is False
    assert result["errors"][0]["code"]


def test_can_read_table_model_honors_graphqlmeta_list_guard(monkeypatch):
    model_cls = SimpleNamespace(
        _meta=SimpleNamespace(app_label="inventory", model_name="product"),
    )
    user = SimpleNamespace(is_authenticated=True, pk=7, id=7, is_superuser=False)

    monkeypatch.setattr(
        access,
        "get_model_graphql_meta",
        lambda model: SimpleNamespace(
            describe_operation_guard=lambda operation, user=None, instance=None: {
                "guarded": True,
                "allowed": operation == "list",
                "reason": None,
            }
        ),
    )

    assert access.can_read_table_model(user, model_cls, operation="list") is True


def test_can_read_table_model_uses_rbac_context_for_model_permission(monkeypatch):
    model_cls = SimpleNamespace(
        _meta=SimpleNamespace(app_label="inventory", model_name="product"),
    )
    user = SimpleNamespace(is_authenticated=True, pk=9, id=9, is_superuser=False)

    monkeypatch.setattr(
        access,
        "get_model_graphql_meta",
        lambda model: SimpleNamespace(
            describe_operation_guard=lambda operation, user=None, instance=None: {
                "guarded": False,
                "allowed": True,
                "reason": None,
            }
        ),
    )
    monkeypatch.setattr(
        access.QueryGeneratorSettings,
        "from_schema",
        classmethod(
            lambda cls, schema_name: SimpleNamespace(
                require_model_permissions=True,
                model_permission_codename="view",
            )
        ),
    )
    seen = {}

    def _has_permission(user, permission_name, permission_context):
        seen["permission_name"] = permission_name
        seen["operation"] = permission_context.operation
        return True

    monkeypatch.setattr(access.role_manager, "has_permission", _has_permission)

    assert access.can_read_table_model(user, model_cls, schema_name="graphiql") is True
    assert seen == {
        "permission_name": "inventory.view_product",
        "operation": "list",
    }
