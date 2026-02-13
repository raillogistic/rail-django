import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Category, Product

from .fixtures.canonical_model import CANONICAL_PRODUCT_FIXTURE

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def schema_harness():
    return build_schema(schema_name="test_form_canonical_crud", apps=["test_app"])


@pytest.fixture
def admin_user():
    User = get_user_model()
    return User.objects.create_superuser(
        username="canonical_admin",
        email="canonical_admin@example.com",
        password="pass12345",
    )


@pytest.fixture
def limited_user():
    User = get_user_model()
    return User.objects.create_user(username="canonical_limited", password="pass12345")


@pytest.fixture
def gql_client(schema_harness, admin_user):
    return RailGraphQLTestClient(
        schema_harness.schema, schema_name="test_form_canonical_crud", user=admin_user
    )


def test_pages_query_and_authorization_path(gql_client, limited_user):
    category = Category.objects.create(name="General", description="")
    Product.objects.create(name="P1", price=10, category=category)

    query = f"""
    query {{
      {CANONICAL_PRODUCT_FIXTURE.page_query}(page: 1, perPage: 10) {{
        pageInfo {{
          totalCount
        }}
      }}
    }}
    """
    denied = gql_client.execute(query, user=limited_user)
    assert denied.get("errors"), "Expected permission denial for page query."

    allowed = gql_client.execute(query)
    assert allowed.get("errors") is None
    assert allowed["data"][CANONICAL_PRODUCT_FIXTURE.page_query]["pageInfo"]["totalCount"] >= 1


def test_create_update_delete_canonical_mutation_paths(gql_client, limited_user):
    category = Category.objects.create(name="Canonical", description="")

    create_mutation = f"""
    mutation($input: CreateProductInput!) {{
      {CANONICAL_PRODUCT_FIXTURE.create_operation}(input: $input) {{
        ok
        object {{ id name }}
        errors {{ field message }}
      }}
    }}
    """
    denied_create = gql_client.execute(
        create_mutation,
        user=limited_user,
        variables={"input": {"name": "Nope", "price": 10}},
    )
    assert denied_create.get("errors") is None
    assert denied_create["data"][CANONICAL_PRODUCT_FIXTURE.create_operation]["ok"] is False
    denied_create_errors = denied_create["data"][CANONICAL_PRODUCT_FIXTURE.create_operation]["errors"]
    assert denied_create_errors
    assert denied_create_errors[0]["field"] in (None, "__all__")

    invalid_create = gql_client.execute(
        create_mutation,
        variables={"input": {"price": 10}},
    )
    assert invalid_create.get("errors")

    created = gql_client.execute(
        create_mutation,
        variables={
            "input": {
                "name": "Canonical Product",
                "price": 10,
                "category": {"connect": str(category.pk)},
            }
        },
    )
    assert created.get("errors") is None
    assert created["data"][CANONICAL_PRODUCT_FIXTURE.create_operation]["ok"] is True
    product_id = created["data"][CANONICAL_PRODUCT_FIXTURE.create_operation]["object"]["id"]

    update_mutation = f"""
    mutation($id: ID!, $input: UpdateProductInput!) {{
      {CANONICAL_PRODUCT_FIXTURE.update_operation}(id: $id, input: $input) {{
        ok
        object {{ id name }}
        errors {{ field message }}
      }}
    }}
    """
    denied_update = gql_client.execute(
        update_mutation,
        user=limited_user,
        variables={"id": product_id, "input": {"name": "Forbidden"}},
    )
    assert denied_update.get("errors") is None
    assert denied_update["data"][CANONICAL_PRODUCT_FIXTURE.update_operation]["ok"] is False
    assert denied_update["data"][CANONICAL_PRODUCT_FIXTURE.update_operation]["errors"]

    invalid_update = gql_client.execute(
        update_mutation,
        variables={"id": product_id, "input": {"name": ""}},
    )
    assert invalid_update.get("errors") is None
    assert invalid_update["data"][CANONICAL_PRODUCT_FIXTURE.update_operation]["ok"] is False
    assert invalid_update["data"][CANONICAL_PRODUCT_FIXTURE.update_operation]["errors"]

    updated = gql_client.execute(
        update_mutation,
        variables={"id": product_id, "input": {"name": "Canonical Product Updated"}},
    )
    assert updated.get("errors") is None
    assert (
        updated["data"][CANONICAL_PRODUCT_FIXTURE.update_operation]["object"]["name"]
        == "Canonical Product Updated"
    )

    delete_mutation = f"""
    mutation($id: ID!) {{
      {CANONICAL_PRODUCT_FIXTURE.delete_operation}(id: $id) {{
        ok
        errors {{ field message }}
      }}
    }}
    """
    denied_delete = gql_client.execute(
        delete_mutation, user=limited_user, variables={"id": product_id}
    )
    assert denied_delete.get("errors") is None
    assert denied_delete["data"][CANONICAL_PRODUCT_FIXTURE.delete_operation]["ok"] is False
    assert denied_delete["data"][CANONICAL_PRODUCT_FIXTURE.delete_operation]["errors"]

    deleted = gql_client.execute(delete_mutation, variables={"id": product_id})
    assert deleted.get("errors") is None
    assert deleted["data"][CANONICAL_PRODUCT_FIXTURE.delete_operation]["ok"] is True
