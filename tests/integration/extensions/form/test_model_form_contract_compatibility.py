import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from rail_django.extensions.form.config import get_form_settings
from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    harness = build_schema(
        schema_name="test_form_contract_compatibility", apps=["test_app"]
    )
    User = get_user_model()
    user = User.objects.create_superuser(
        username="compat_admin",
        email="compat_admin@example.com",
        password="pass12345",
    )
    return RailGraphQLTestClient(
        harness.schema, schema_name="test_form_contract_compatibility", user=user
    )


@pytest.fixture(autouse=True)
def clear_form_settings_cache():
    get_form_settings.cache_clear()
    yield
    get_form_settings.cache_clear()


def test_generated_form_metadata_disabled_falls_back_to_legacy_form_config(gql_client):
    previous = getattr(Product.GraphQLMeta, "custom_metadata", None)
    Product.GraphQLMeta.custom_metadata = {"generated_form": {"enabled": False}}
    if hasattr(Product, "_graphql_meta_instance"):
        delattr(Product, "_graphql_meta_instance")

    try:
        generated_query = """
        query {
          modelFormContract(appLabel: "test_app", modelName: "Product") {
            id
          }
        }
        """
        generated_result = gql_client.execute(generated_query)
        assert generated_result.get("errors"), "Expected disabled model to reject query."

        legacy_query = """
        query {
          formConfig(app: "test_app", model: "Product") {
            id
            app
            model
          }
        }
        """
        legacy_result = gql_client.execute(legacy_query)
        assert legacy_result.get("errors") is None
        assert legacy_result["data"]["formConfig"]["model"] == "Product"
    finally:
        if previous is None and hasattr(Product.GraphQLMeta, "custom_metadata"):
            delattr(Product.GraphQLMeta, "custom_metadata")
        else:
            Product.GraphQLMeta.custom_metadata = previous
        if hasattr(Product, "_graphql_meta_instance"):
            delattr(Product, "_graphql_meta_instance")


@override_settings(
    RAIL_DJANGO_FORM={
        "generated_form_excluded_models": ["test_app.Product"],
    }
)
def test_generated_form_excluded_model_falls_back_to_legacy_form_config(gql_client):
    generated_query = """
    query {
      modelFormContract(appLabel: "test_app", modelName: "Product") {
        id
      }
    }
    """
    generated_result = gql_client.execute(generated_query)
    assert generated_result.get("errors"), "Expected excluded model to reject query."

    legacy_query = """
    query {
      formConfig(app: "test_app", model: "Product") {
        id
        app
        model
      }
    }
    """
    legacy_result = gql_client.execute(legacy_query)
    assert legacy_result.get("errors") is None
    assert legacy_result["data"]["formConfig"]["model"] == "Product"
