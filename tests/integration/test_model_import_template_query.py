import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def auth_client():
    harness = build_schema(schema_name="test_import_template", apps=["test_app"])
    user = get_user_model().objects.create_superuser(
        username="import_template_admin",
        email="import_template_admin@example.com",
        password="pass",
    )
    return RailGraphQLTestClient(
        harness.schema,
        schema_name="test_import_template",
        user=user,
    )


@pytest.fixture
def anonymous_client():
    harness = build_schema(schema_name="test_import_template_anonymous", apps=["test_app"])
    return RailGraphQLTestClient(harness.schema, schema_name="test_import_template_anonymous")


TEMPLATE_QUERY = """
query ModelImportTemplate($appLabel: String!, $modelName: String!) {
  modelImportTemplate(appLabel: $appLabel, modelName: $modelName) {
    templateId
    appLabel
    modelName
    version
    exactVersion
    matchingKeyFields
    acceptedFormats
    maxRows
    maxFileSizeBytes
    downloadUrl
    requiredColumns {
      name
      label
      defaultValue
    }
    optionalColumns {
      name
      label
      defaultValue
    }
  }
}
"""


def test_model_import_template_query_returns_payload(auth_client):
    result = auth_client.execute(
        TEMPLATE_QUERY,
        variables={"appLabel": "test_app", "modelName": "Product"},
    )
    assert result.get("errors") is None
    payload = result["data"]["modelImportTemplate"]
    assert payload["appLabel"] == "test_app"
    assert payload["modelName"] == "Product"
    assert payload["version"] == payload["exactVersion"]
    assert "CSV" in payload["acceptedFormats"]
    assert "XLSX" in payload["acceptedFormats"]
    assert payload["maxRows"] > 0
    assert payload["maxFileSizeBytes"] > 0
    assert payload["downloadUrl"]
    assert any(column["name"] == "name" and column["label"] for column in payload["requiredColumns"])
    inventory_column = next(
        column for column in payload["optionalColumns"] if column["name"] == "inventory_count"
    )
    assert inventory_column["defaultValue"] is not None


def test_model_import_template_query_requires_authentication(anonymous_client):
    result = anonymous_client.execute(
        TEMPLATE_QUERY,
        variables={"appLabel": "test_app", "modelName": "Product"},
    )
    assert result.get("errors") is not None
