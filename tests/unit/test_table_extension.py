from types import SimpleNamespace
from decimal import Decimal

from rail_django.extensions.table.cache.store import clear_cache_prefix
from rail_django.extensions.table.services.bootstrap import build_table_bootstrap_payload
from rail_django.extensions.table.services.data_resolver import resolve_table_rows
from rail_django.extensions.table.services.action_executor import execute_table_action


class FakeField:
    def __init__(self, name: str, type_name: str) -> None:
        self.name = name
        self.verbose_name = name
        self._type_name = type_name

    def get_internal_type(self) -> str:
        return self._type_name


class FakeQuerySet:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def all(self):
        return self

    def filter(self, **kwargs):
        if "pk__in" in kwargs:
            ids = set(kwargs["pk__in"])
            return FakeQuerySet([row for row in self._rows if row["id"] in ids])
        return self

    def order_by(self, *args):
        return self

    def count(self):
        return len(self._rows)

    def values(self, *keys):
        if not keys:
            return self._rows
        return [{key: row.get(key) for key in keys} for row in self._rows]

    def distinct(self, *args):
        return self

    def values_list(self, key, flat=False):
        resolved_key = "id" if key == "pk" else key
        return [row[resolved_key] for row in self._rows]

    def delete(self):
        return (len(self._rows), {})

    def __getitem__(self, item):
        if isinstance(item, slice):
            return FakeQuerySet(self._rows[item])
        return self._rows[item]


class FakeModel:
    _meta = SimpleNamespace(
        fields=[FakeField("id", "AutoField"), FakeField("name", "CharField")],
        app_label="tests",
        model_name="testcustomer",
    )
    objects = FakeQuerySet([{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])


ALLOWED_TABLE_PERMISSIONS = SimpleNamespace(
    can_view=True,
    can_create=True,
    can_export=True,
    can_delete=True,
)


def test_table_bootstrap_payload_has_columns(monkeypatch):
    clear_cache_prefix("table:bootstrap:")
    monkeypatch.setattr(
        "rail_django.extensions.table.services.bootstrap.resolve_table_model",
        lambda app, model: FakeModel,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.bootstrap.get_table_permissions",
        lambda user, model_cls: ALLOWED_TABLE_PERMISSIONS,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.bootstrap.get_visible_table_fields",
        lambda user, model_cls: (["id", "name"], {"name"}, set()),
    )
    payload = build_table_bootstrap_payload("tests", "TestCustomer")
    assert payload["tableConfig"]["app"] == "tests"
    assert payload["tableConfig"]["model"] == "TestCustomer"
    assert len(payload["tableConfig"]["columns"]) == 2


def test_table_bootstrap_payload_uses_user_table_state(monkeypatch):
    clear_cache_prefix("table:bootstrap:")
    monkeypatch.setattr(
        "rail_django.extensions.table.services.bootstrap.resolve_table_model",
        lambda app, model: FakeModel,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.bootstrap.get_table_permissions",
        lambda user, model_cls: ALLOWED_TABLE_PERMISSIONS,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.bootstrap.get_visible_table_fields",
        lambda user, model_cls: (["id", "name"], {"name"}, set()),
    )
    user = SimpleNamespace(
        id=7,
        is_authenticated=True,
        settings=SimpleNamespace(
            table_configs={
                "tests-TestCustomer-/customers": {
                    "columnOrder": ["name", "id"],
                    "columnVisibility": {"name": True, "id": False},
                    "columnWidths": {"name": 280},
                    "perPage": 50,
                    "density": "compact",
                    "wrapCells": False,
                    "visibilityVersion": 3,
                }
            }
        ),
    )

    payload = build_table_bootstrap_payload(
        "tests",
        "TestCustomer",
        user=user,
        persistence_key="tests-TestCustomer-/customers",
    )

    assert payload["initialState"]["pageSize"] == 50
    assert payload["initialState"]["columnOrder"] == ["name", "id"]
    assert payload["initialState"]["columnVisibility"] == {"name": True, "id": False}
    assert payload["initialState"]["columnWidths"] == {"name": 280}
    assert payload["initialState"]["density"] == "compact"
    assert payload["initialState"]["wrapCells"] is False
    assert payload["initialState"]["visibilityVersion"] == 3
    assert (
        payload["initialState"]["persistenceKey"]
        == "tests-TestCustomer-/customers"
    )


def test_table_bootstrap_payload_normalizes_persistence_key_variants(monkeypatch):
    clear_cache_prefix("table:bootstrap:")
    monkeypatch.setattr(
        "rail_django.extensions.table.services.bootstrap.resolve_table_model",
        lambda app, model: FakeModel,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.bootstrap.get_table_permissions",
        lambda user, model_cls: ALLOWED_TABLE_PERMISSIONS,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.bootstrap.get_visible_table_fields",
        lambda user, model_cls: (["id", "name"], {"name"}, set()),
    )
    user = SimpleNamespace(
        id=9,
        is_authenticated=True,
        settings=SimpleNamespace(
            table_configs={
                "tests-TestCustomer-/customers/": {
                    "perPage": 40,
                    "density": "comfortable",
                    "wrapCells": True,
                }
            }
        ),
    )

    payload = build_table_bootstrap_payload(
        "tests",
        "TestCustomer",
        user=user,
        persistence_key="tests-TestCustomer-/customers",
    )

    assert payload["initialState"]["pageSize"] == 40
    assert payload["initialState"]["density"] == "comfortable"
    assert payload["initialState"]["wrapCells"] is True
    assert payload["initialState"]["persistenceKey"] == "tests-TestCustomer-/customers/"


def test_table_bootstrap_cache_is_scoped_by_persistence_key(monkeypatch):
    clear_cache_prefix("table:bootstrap:")
    monkeypatch.setattr(
        "rail_django.extensions.table.services.bootstrap.resolve_table_model",
        lambda app, model: FakeModel,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.bootstrap.get_table_permissions",
        lambda user, model_cls: ALLOWED_TABLE_PERMISSIONS,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.bootstrap.get_visible_table_fields",
        lambda user, model_cls: (["id", "name"], {"name"}, set()),
    )
    user = SimpleNamespace(
        id=11,
        is_authenticated=True,
        settings=SimpleNamespace(
            table_configs={
                "tests-TestCustomer-/customers-a": {"perPage": 15},
                "tests-TestCustomer-/customers-b": {"perPage": 60},
            }
        ),
    )

    payload_a = build_table_bootstrap_payload(
        "tests",
        "TestCustomer",
        user=user,
        persistence_key="tests-TestCustomer-/customers-a",
    )
    payload_b = build_table_bootstrap_payload(
        "tests",
        "TestCustomer",
        user=user,
        persistence_key="tests-TestCustomer-/customers-b",
    )

    assert payload_a["initialState"]["pageSize"] == 15
    assert payload_b["initialState"]["pageSize"] == 60


def test_table_rows_returns_paginated_items(monkeypatch):
    monkeypatch.setattr(
        "rail_django.extensions.table.services.data_resolver.resolve_table_model",
        lambda app, model: FakeModel,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.data_resolver.get_table_permissions",
        lambda user, model_cls: ALLOWED_TABLE_PERMISSIONS,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.data_resolver.get_visible_table_fields",
        lambda user, model_cls: (["id", "name"], {"name"}, set()),
    )
    response = resolve_table_rows({"app": "tests", "model": "TestCustomer", "pageSize": 1})
    assert response["pageInfo"]["totalCount"] == 2
    assert len(response["items"]) == 1


def test_table_action_delete_removes_rows(monkeypatch):
    monkeypatch.setattr(
        "rail_django.extensions.table.services.action_executor.resolve_table_model",
        lambda app, model: FakeModel,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.action_executor.get_table_permissions",
        lambda user, model_cls: ALLOWED_TABLE_PERMISSIONS,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.action_executor.table_mutations_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.action_executor.is_rate_limited",
        lambda scope: False,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.action_executor.detect_action_anomaly",
        lambda action_id, row_ids, payload: False,
    )
    result = execute_table_action(
        {
            "app": "tests",
            "model": "TestCustomer",
            "actionId": "delete",
            "rowIds": [1],
        }
    )
    assert result["ok"] is True
    assert result["affectedIds"] == ["1"]


def test_table_rows_serializes_decimal_values(monkeypatch):
    class DecimalModel:
        _meta = SimpleNamespace(
            fields=[FakeField("id", "AutoField"), FakeField("price", "DecimalField")]
        )
        objects = FakeQuerySet([{"id": 1, "price": Decimal("10.50")}])

    monkeypatch.setattr(
        "rail_django.extensions.table.services.data_resolver.resolve_table_model",
        lambda app, model: DecimalModel,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.data_resolver.get_table_permissions",
        lambda user, model_cls: ALLOWED_TABLE_PERMISSIONS,
    )
    monkeypatch.setattr(
        "rail_django.extensions.table.services.data_resolver.get_visible_table_fields",
        lambda user, model_cls: (["id", "price"], set(), set()),
    )
    response = resolve_table_rows({"app": "tests", "model": "Product", "pageSize": 10})
    assert response["items"][0]["price"] == "10.50"
