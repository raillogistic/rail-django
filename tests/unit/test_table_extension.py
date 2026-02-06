from types import SimpleNamespace
from decimal import Decimal

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

    def values(self):
        return self._rows

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
        fields=[FakeField("id", "AutoField"), FakeField("name", "CharField")]
    )
    objects = FakeQuerySet([{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])


def test_table_bootstrap_payload_has_columns(monkeypatch):
    monkeypatch.setattr(
        "rail_django.extensions.table.services.bootstrap.apps.get_model",
        lambda app, model: FakeModel,
    )
    payload = build_table_bootstrap_payload("tests", "TestCustomer")
    assert payload["tableConfig"]["app"] == "tests"
    assert payload["tableConfig"]["model"] == "TestCustomer"
    assert len(payload["tableConfig"]["columns"]) == 2


def test_table_rows_returns_paginated_items(monkeypatch):
    monkeypatch.setattr(
        "rail_django.extensions.table.services.data_resolver.apps.get_model",
        lambda app, model: FakeModel,
    )
    response = resolve_table_rows({"app": "tests", "model": "TestCustomer", "pageSize": 1})
    assert response["pageInfo"]["totalCount"] == 2
    assert len(response["items"]) == 1


def test_table_action_delete_removes_rows(monkeypatch):
    monkeypatch.setattr(
        "rail_django.extensions.table.services.action_executor.apps.get_model",
        lambda app, model: FakeModel,
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
        "rail_django.extensions.table.services.data_resolver.apps.get_model",
        lambda app, model: DecimalModel,
    )
    response = resolve_table_rows({"app": "tests", "model": "Product", "pageSize": 10})
    assert response["items"][0]["price"] == "10.50"
