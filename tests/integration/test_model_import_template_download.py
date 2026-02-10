import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from rail_django.extensions.auth import JWTManager
from rail_django.extensions.excel.builder import OPENPYXL_AVAILABLE
from rail_django.extensions.importing.views import ModelImportTemplateDownloadView

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _bearer_token_for_user(user) -> str:
    return JWTManager.generate_token(user)["token"]


def test_model_import_template_download_returns_csv():
    user = get_user_model().objects.create_superuser(
        username="import_template_download_admin",
        email="import_template_download_admin@example.com",
        password="pass",
    )
    token = _bearer_token_for_user(user)

    request = RequestFactory().get(
        "/api/v1/import/templates/test_app/product/",
        {"format": "csv"},
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    response = ModelImportTemplateDownloadView.as_view()(
        request,
        app_label="test_app",
        model_name="product",
    )

    assert response.status_code == 200
    assert response["Content-Disposition"] == (
        'attachment; filename="test_app-product-import-template.csv"'
    )

    header_row = response.content.decode("utf-8-sig").splitlines()[0]
    assert "name" in header_row
    assert "price" in header_row


@pytest.mark.skipif(not OPENPYXL_AVAILABLE, reason="openpyxl is required for xlsx rendering")
def test_model_import_template_download_returns_xlsx():
    user = get_user_model().objects.create_superuser(
        username="import_template_download_admin_xlsx",
        email="import_template_download_admin_xlsx@example.com",
        password="pass",
    )
    token = _bearer_token_for_user(user)

    request = RequestFactory().get(
        "/api/v1/import/templates/test_app/product/",
        {"format": "xlsx"},
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    response = ModelImportTemplateDownloadView.as_view()(
        request,
        app_label="test_app",
        model_name="product",
    )

    assert response.status_code == 200
    assert (
        response["Content-Type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response["Content-Disposition"] == (
        'attachment; filename="test_app-product-import-template.xlsx"'
    )
    # XLSX files are ZIP containers and begin with PK magic bytes.
    assert response.content.startswith(b"PK")


def test_model_import_template_download_requires_authentication():
    request = RequestFactory().get(
        "/api/v1/import/templates/test_app/product/",
        {"format": "csv"},
    )
    response = ModelImportTemplateDownloadView.as_view()(
        request,
        app_label="test_app",
        model_name="product",
    )

    assert response.status_code == 401
