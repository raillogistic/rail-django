"""
Integration tests for PDF templating endpoints.
"""

import os
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings

from rail_django.extensions.auth import JWTManager
from rail_django.extensions.templating import (
    PdfTemplateView,
    WEASYPRINT_AVAILABLE,
    pdf_template,
    template_registry,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.skipif(not WEASYPRINT_AVAILABLE, reason="WeasyPrint not available")
@override_settings(
    TEMPLATES=[
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [],
            "APP_DIRS": False,
            "OPTIONS": {
                "loaders": [
                    (
                        "django.template.loaders.locmem.Loader",
                        {
                            "pdf/header.html": "<div>Header {{ data.title }}</div>",
                            "pdf/content.html": "<div>Content {{ data.title }}</div>",
                            "pdf/footer.html": "<div>Footer</div>",
                        },
                    )
                ]
            },
        }
    ],
    RAIL_DJANGO_GRAPHQL_TEMPLATING={
        "renderer": "weasyprint",
        "rate_limit": {"enable": False},
    },
)
def test_pdf_template_view_returns_pdf_response():
    original_templates = template_registry.all()
    try:

        @pdf_template(
            content="pdf/content.html",
            header="pdf/header.html",
            footer="pdf/footer.html",
            url="testing/pdf",
            require_authentication=True,
        )
        def sample_template(request, pk):
            return {"title": f"Item {pk}"}

        User = get_user_model()
        user = User.objects.create_user(username="pdf_user", password="pass12345")
        token = JWTManager.generate_token(user)["token"]

        request = RequestFactory().get(
            "/api/templates/testing/pdf/1/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        response = PdfTemplateView.as_view()(
            request, template_path="testing/pdf", pk="1"
        )

        assert response.status_code == 200
        assert response["Content-Disposition"] == 'inline; filename="testing-pdf-1.pdf"'
        assert response.content.startswith(b"%PDF")
        artifacts_dir = Path(
            os.environ.get("RAIL_DJANGO_TEST_ARTIFACTS_DIR", "tests/artifacts")
        )
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        file_path = artifacts_dir / "testing-pdf-1.pdf"
        file_path.write_bytes(response.content)
        assert file_path.exists()
        assert file_path.stat().st_size > 0
    finally:
        template_registry._templates = dict(original_templates)
