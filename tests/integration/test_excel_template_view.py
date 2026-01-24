"""
Integration tests for Excel template endpoints.
"""

import os
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings

from rail_django.extensions.auth import JWTManager
from rail_django.extensions.excel import (
    ExcelTemplateView,
    OPENPYXL_AVAILABLE,
    excel_template_registry,
    model_excel_template,
)
from rail_django.extensions.excel.exporter import _register_model_excel_templates
from tests.models import TestCustomer

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@override_settings(
    RAIL_DJANGO_GRAPHQL_EXCEL_EXPORT={
        "rate_limit": {"enable": False},
    }
)
def test_model_excel_template_view_returns_excel_response():
    if not OPENPYXL_AVAILABLE:
        pytest.skip("openpyxl not available")

    original_templates = excel_template_registry.all()
    try:
        # Attach a model template at runtime and register it
        def export_customer(self):
            return [["Nom"], [self.nom_client]]

        export_customer = model_excel_template(
            url="testing/customer_excel",
            require_authentication=True,
        )(export_customer)
        TestCustomer.export_customer = export_customer
        _register_model_excel_templates(TestCustomer)

        User = get_user_model()
        user = User.objects.create_user(username="excel_user", password="pass12345")
        token = JWTManager.generate_token(user)["token"]

        customer = TestCustomer.objects.create(
            nom_client="Charlie",
            prenom_client="Chloe",
            email_client="charlie@example.com",
        )

        rf = RequestFactory()
        request = rf.get(
            "/api/excel/testing/customer_excel/",
            {"pk": customer.pk},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        response = ExcelTemplateView.as_view()(
            request, template_path="testing/customer_excel"
        )

        assert response.status_code == 200
        assert response["Content-Disposition"] == (
            f'attachment; filename="testcustomer-{customer.pk}.xlsx"'
        )
        assert response.content.startswith(b"PK")

        artifacts_dir = Path(
            os.environ.get("RAIL_DJANGO_TEST_ARTIFACTS_DIR", "tests/artifacts")
        )
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        file_path = artifacts_dir / "customer_template.xlsx"
        file_path.write_bytes(response.content)
        assert file_path.exists()
        assert file_path.stat().st_size > 0
    finally:
        excel_template_registry._templates = dict(original_templates)
        if hasattr(TestCustomer, "export_customer"):
            delattr(TestCustomer, "export_customer")
