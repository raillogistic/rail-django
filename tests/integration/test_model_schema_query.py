import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    harness = build_schema(schema_name="test_model_schema", apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="metadata_admin",
        email="metadata@example.com",
        password="pass12345",
    )
    return RailGraphQLTestClient(
        harness.schema, schema_name="test_model_schema", user=user
    )


def test_model_schema_query_is_available_by_default(gql_client):
    query = """
    query {
      modelSchema(app: "test_app", model: "Product") {
        app
        model
        metadataVersion
        fields {
          name
        }
      }
    }
    """

    result = gql_client.execute(query)

    assert result.get("errors") is None
    data = result["data"]["modelSchema"]
    assert data["app"] == "test_app"
    assert data["model"] == "Product"
    assert isinstance(data["metadataVersion"], str)
    assert any(field["name"] == "name" for field in data["fields"])
