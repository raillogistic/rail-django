"""
Integration tests for reporting dataset execution engine.
"""

from types import SimpleNamespace

import pytest
from django.db.models import F, Value

from rail_django.extensions.reporting import DatasetExecutionEngine, ReportingDataset
from tests.models import TestCustomer

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_dataset_records_query_returns_rows():
    TestCustomer.objects.create(
        nom_client="Alpha",
        prenom_client="Alice",
        email_client="alpha@example.com",
    )
    TestCustomer.objects.create(
        nom_client="Beta",
        prenom_client="Bob",
        email_client="beta@example.com",
    )
    TestCustomer.objects.create(
        nom_client="Gamma",
        prenom_client="Gina",
        email_client="gamma@example.com",
    )

    dataset = ReportingDataset.objects.create(
        code="customers",
        title="Customers",
        description="Customer records",
        source_app_label="tests",
        source_model="TestCustomer",
        metadata={"fields": ["nom_client", "email_client"]},
    )

    engine = DatasetExecutionEngine(dataset)
    payload = engine.run_query(
        {
            "mode": "records",
            "fields": ["nom_client", "email_client"],
            "ordering": ["nom_client"],
            "limit": 2,
            "offset": -10,
        }
    )

    assert payload["mode"] == "records"
    assert payload["fields"] == ["nom_client", "email_client"]
    assert len(payload["rows"]) == 2
    assert payload["rows"][0]["nom_client"] == "Alpha"
    assert payload["offset"] == 0
    assert payload["returned_count"] == 2
    assert payload["has_more"] is True


def test_aggregate_mode_uses_lookahead_pagination():
    for name in ("Alpha", "Beta", "Gamma"):
        TestCustomer.objects.create(
            nom_client=name,
            prenom_client=name,
            email_client=f"{name.lower()}-aggregate-page@example.com",
        )

    dataset = ReportingDataset.objects.create(
        code="customer-groups",
        title="Customer groups",
        source_app_label="tests",
        source_model="TestCustomer",
        dimensions=[{"name": "name", "field": "nom_client"}],
        metrics=[{"name": "count", "field": "id", "aggregation": "count"}],
    )

    payload = DatasetExecutionEngine(dataset).run_query(
        {
            "dimensions": ["name"],
            "metrics": ["count"],
            "ordering": ["nom_client"],
            "limit": 2,
        }
    )

    assert len(payload["rows"]) == 2
    assert payload["returned_count"] == 2
    assert payload["has_more"] is True


def test_non_orm_mode_uses_lookahead_and_clamps_negative_limit():
    dataset = ReportingDataset.objects.create(
        code="external-page",
        title="External page",
        source_app_label="tests",
        source_model="TestCustomer",
    )
    engine = DatasetExecutionEngine(dataset)
    engine._source_adapter = SimpleNamespace(
        supports_orm_operations=lambda: False,
        get_base_queryset=lambda context=None: [{"id": 1}, {"id": 2}, {"id": 3}],
    )

    payload = engine.run_query({"mode": "records", "limit": 2, "offset": -1})
    assert payload["rows"] == [{"id": 1}, {"id": 2}]
    assert payload["offset"] == 0
    assert payload["returned_count"] == 2
    assert payload["has_more"] is True

    empty_page = engine.run_query({"mode": "records", "limit": -1})
    assert empty_page["rows"] == []
    assert empty_page["limit"] == 0
    assert empty_page["returned_count"] == 0
    assert empty_page["has_more"] is True


def test_global_aggregate_returns_one_row_and_preserves_empty_ordering():
    TestCustomer.objects.create(
        nom_client="Alpha",
        prenom_client="Alice",
        email_client="alpha-summary@example.com",
        solde_compte="10.00",
    )
    TestCustomer.objects.create(
        nom_client="Beta",
        prenom_client="Bob",
        email_client="beta-summary@example.com",
        solde_compte="30.00",
    )
    dataset = ReportingDataset.objects.create(
        code="customer-summary",
        title="Customer summary",
        source_app_label="tests",
        source_model="TestCustomer",
        dimensions=[{"name": "id", "field": "id"}],
        metrics=[
            {"name": "count", "field": "id", "aggregation": "count"},
            {"name": "total", "field": "solde_compte", "aggregation": "sum"},
            {"name": "average", "field": "solde_compte", "aggregation": "avg"},
        ],
        ordering=["nom_client"],
    )

    payload = DatasetExecutionEngine(dataset).run_query(
        {
            "dimensions": [],
            "metrics": ["count", "total", "average"],
            "ordering": [],
        }
    )

    assert payload["rows"] == [{"count": 2, "total": 40, "average": 20}]
    assert payload["ordering"] == []
    assert payload["returned_count"] == 1
    assert payload["has_more"] is False
    assert payload["warnings"] == []


def test_records_mode_accepts_allowlisted_queryset_annotations():
    TestCustomer.objects.create(
        nom_client="Alpha",
        prenom_client="Alice",
        email_client="alpha-annotation@example.com",
        solde_compte="10.00",
    )
    original = getattr(TestCustomer, "filter_reporting_queryset", None)
    TestCustomer.filter_reporting_queryset = classmethod(
        lambda cls, queryset, user: queryset.annotate(
            reporting_balance=F("solde_compte") + Value(5)
        )
    )
    try:
        dataset = ReportingDataset.objects.create(
            code="customer-annotations",
            title="Customer annotations",
            source_app_label="tests",
            source_model="TestCustomer",
            metadata={"record_fields": ["nom_client", "reporting_balance"]},
        )
        payload = DatasetExecutionEngine(
            dataset, context=SimpleNamespace(user=None)
        ).run_query(
            {
                "mode": "records",
                "fields": ["nom_client", "reporting_balance", "not_allowed"],
                "ordering": [],
            }
        )
    finally:
        if original is None:
            delattr(TestCustomer, "filter_reporting_queryset")
        else:
            TestCustomer.filter_reporting_queryset = original

    assert payload["fields"] == ["nom_client", "reporting_balance"]
    assert payload["rows"][0]["reporting_balance"] == 15
    assert payload["warnings"] == ["Champ invalide: not_allowed"]
