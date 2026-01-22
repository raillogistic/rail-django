"""
Integration tests for reporting dataset execution engine.
"""

import pytest

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


