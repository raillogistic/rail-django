"""
Integration tests for export view endpoints.
"""

import json
import os
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings

from rail_django.extensions.auth import JWTManager
from rail_django.extensions.exporting import EXCEL_AVAILABLE, ExportView
from tests.models import TestCustomer

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _export_settings():
    return {
        "export_fields": {"tests.testcustomer": ["nom_client", "email_client"]},
        "require_export_fields": True,
        "require_model_permissions": False,
        "require_field_permissions": False,
        "stream_csv": False,
        "enforce_streaming_csv": False,
        "allowed_models": ["tests.testcustomer"],
        "async_jobs": {"enable": False},
    }


@override_settings(RAIL_DJANGO_EXPORT=_export_settings())
def test_export_view_returns_csv_response():
    User = get_user_model()
    user = User.objects.create_user(username="export_user", password="pass12345")
    token = JWTManager.generate_token(user)["token"]

    TestCustomer.objects.create(
        nom_client="Alpha",
        prenom_client="Alice",
        email_client="alpha@example.com",
    )

    payload = {
        "app_name": "tests",
        "model_name": "TestCustomer",
        "file_extension": "csv",
        "filename": "customers",
        "fields": ["nom_client", "email_client"],
    }

    rf = RequestFactory()
    request = rf.post(
        "/export/",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    response = ExportView.as_view()(request)
    assert response.status_code == 200
    assert response["Content-Disposition"] == 'attachment; filename="customers.csv"'
    assert b"Alpha" in response.content


@override_settings(RAIL_DJANGO_EXPORT=_export_settings())
def test_export_view_returns_excel_response():
    if not EXCEL_AVAILABLE:
        pytest.skip("openpyxl not available")
    User = get_user_model()
    user = User.objects.create_user(username="export_excel", password="pass12345")
    token = JWTManager.generate_token(user)["token"]

    TestCustomer.objects.create(
        nom_client="Bravo",
        prenom_client="Bob",
        email_client="bravo@example.com",
    )

    payload = {
        "app_name": "tests",
        "model_name": "TestCustomer",
        "file_extension": "xlsx",
        "filename": "customers",
        "fields": ["nom_client", "email_client"],
    }

    rf = RequestFactory()
    request = rf.post(
        "/export/",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    response = ExportView.as_view()(request)
    assert response.status_code == 200
    assert response["Content-Disposition"] == 'attachment; filename="customers.xlsx"'
    assert response.content.startswith(b"PK")
    artifacts_dir = Path(
        os.environ.get("RAIL_DJANGO_TEST_ARTIFACTS_DIR", "tests/artifacts")
    )
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    file_path = artifacts_dir / "customers.xlsx"
    file_path.write_bytes(response.content)
    assert file_path.exists()
    assert file_path.stat().st_size > 0


