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
        }
    )

    assert payload["mode"] == "records"
    assert payload["fields"] == ["nom_client", "email_client"]
    assert len(payload["rows"]) == 2
    assert payload["rows"][0]["nom_client"] == "Alpha"


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


