import pytest
import graphene
from django.contrib.auth import get_user_model
from django.db import models

from rail_django.extensions.templating import model_pdf_template
from rail_django.extensions.templating.registry import (
    _register_model_templates,
    template_registry,
)
from rail_django.extensions.excel import model_excel_template
from rail_django.extensions.excel.exporter import (
    _register_model_excel_templates,
    excel_template_registry,
)
from rail_django.extensions.metadata.utils import invalidate_metadata_cache
from rail_django.testing import RailGraphQLTestClient, build_schema

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    harness = build_schema(schema_name="test_class_templates", apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="template_admin",
        email="template@example.com",
        password="pass12345",
    )
    return RailGraphQLTestClient(
        harness.schema, schema_name="test_class_templates", user=user
    )


def test_model_templates_query_detects_class_level_pdf_template(gql_client):
    from test_app.models import Product

    original_templates = template_registry.all()
    original_meta = getattr(Product, "_pdf_template_meta", None)

    # Decorate the class
    model_pdf_template(
        content="pdf/product_restitution.html",
        title="Bon de restitution",
    )(Product)

    _register_model_templates(Product)
    invalidate_metadata_cache(app="test_app", model="Product")

    query = """
    query {
      modelTemplates(app: "test_app", model: "Product") {
        key
        templateType
        title
        urlPath
      }
    }
    """

    try:
        result = gql_client.execute(query)
        assert result.get("errors") is None
        payload = result["data"]["modelTemplates"]

        # Check if our class-level template is there
        found = [t for t in payload if t["title"] == "Bon de restitution"]
        assert len(found) == 1
        assert found[0]["templateType"] == "pdf"
        assert found[0]["urlPath"].endswith("/print")

    finally:
        if original_meta is None:
            if hasattr(Product, "_pdf_template_meta"):
                delattr(Product, "_pdf_template_meta")
        else:
            Product._pdf_template_meta = original_meta

        template_registry._templates = dict(original_templates)
        invalidate_metadata_cache(app="test_app", model="Product")


def test_model_templates_query_detects_class_level_excel_template(gql_client):
    from test_app.models import Product

    original_excel_templates = excel_template_registry.all()
    original_excel_meta = getattr(Product, "_excel_template_meta", None)

    # Decorate the class
    model_excel_template(
        title="Full Product Export",
    )(Product)

    _register_model_excel_templates(Product)
    invalidate_metadata_cache(app="test_app", model="Product")

    query = """
    query {
      modelTemplates(app: "test_app", model: "Product") {
        key
        templateType
        title
        urlPath
      }
    }
    """

    try:
        result = gql_client.execute(query)
        assert result.get("errors") is None
        payload = result["data"]["modelTemplates"]

        # Check if our class-level Excel template is there
        found = [t for t in payload if t["title"] == "Full Product Export"]
        assert len(found) == 1
        assert found[0]["templateType"] == "excel"
        assert found[0]["urlPath"].endswith("/export")

    finally:
        if original_excel_meta is None:
            if hasattr(Product, "_excel_template_meta"):
                delattr(Product, "_excel_template_meta")
        else:
            Product._excel_template_meta = original_excel_meta

        excel_template_registry._templates = dict(original_excel_templates)
        invalidate_metadata_cache(app="test_app", model="Product")
