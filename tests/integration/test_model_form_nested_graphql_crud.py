import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Category, Post, Tag

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def schema_harness():
    return build_schema(schema_name="test_model_form_nested_graphql_crud", apps=["test_app"])


@pytest.fixture
def admin_user():
    User = get_user_model()
    return User.objects.create_superuser(
        username="nested_crud_admin",
        email="nested_crud_admin@example.com",
        password="pass12345",
    )


@pytest.fixture
def limited_user():
    User = get_user_model()
    return User.objects.create_user(username="nested_crud_limited", password="pass12345")


@pytest.fixture
def gql_client(schema_harness, admin_user):
    return RailGraphQLTestClient(
        schema_harness.schema,
        schema_name="test_model_form_nested_graphql_crud",
        user=admin_user,
    )


def test_post_page_create_update_delete_graphql_paths(gql_client, limited_user):
    category = Category.objects.create(name="Nested", description="")
    existing_tag = Tag.objects.create(name="existing-tag")
    Post.objects.create(title="Existing", category=category)

    denied_page_query = gql_client.execute(
        """
        query {
          postPage(page: 1, perPage: 20) {
            pageInfo { totalCount }
          }
        }
        """,
        user=limited_user,
    )
    assert denied_page_query.get("errors"), "Expected page query to be denied for limited user."

    allowed_page_query = gql_client.execute(
        """
        query {
          postPage(page: 1, perPage: 20) {
            pageInfo { totalCount }
          }
        }
        """
    )
    assert allowed_page_query.get("errors") is None
    assert allowed_page_query["data"]["postPage"]["pageInfo"]["totalCount"] >= 1

    create_mutation = """
    mutation($input: CreatePostInput!) {
      createPost(input: $input) {
        ok
        object {
          id
          title
          tags { id name }
        }
        errors { field message code }
      }
    }
    """
    created = gql_client.execute(
        create_mutation,
        variables={
            "input": {
                "title": "Nested GraphQL Post",
                "category": {"connect": str(category.pk)},
                "tags": {
                    "connect": [str(existing_tag.pk)],
                    "create": [{"name": "created-inline"}],
                },
            }
        },
    )
    assert created.get("errors") is None
    created_payload = created["data"]["createPost"]
    assert created_payload["ok"] is True
    created_tag_names = {entry["name"] for entry in created_payload["object"]["tags"]}
    assert {"existing-tag", "created-inline"}.issubset(created_tag_names)
    post_id = created_payload["object"]["id"]

    replacement_tag = Tag.objects.create(name="replacement-tag")
    update_mutation = """
    mutation($id: ID!, $input: UpdatePostInput!) {
      updatePost(id: $id, input: $input) {
        ok
        object {
          id
          title
          tags { id name }
        }
        errors { field message code }
      }
    }
    """
    updated = gql_client.execute(
        update_mutation,
        variables={
            "id": post_id,
            "input": {
                "title": "Nested GraphQL Post Updated",
                "tags": {"set": [str(replacement_tag.pk)]},
            },
        },
    )
    assert updated.get("errors") is None
    updated_payload = updated["data"]["updatePost"]
    assert updated_payload["ok"] is True
    assert updated_payload["object"]["title"] == "Nested GraphQL Post Updated"
    assert [entry["name"] for entry in updated_payload["object"]["tags"]] == [
        "replacement-tag"
    ]

    deleted = gql_client.execute(
        """
        mutation($id: ID!) {
          deletePost(id: $id) {
            ok
            errors { field message code }
          }
        }
        """,
        variables={"id": post_id},
    )
    assert deleted.get("errors") is None
    assert deleted["data"]["deletePost"]["ok"] is True


def test_post_nested_mutation_validation_and_authorization_paths(gql_client, limited_user):
    category = Category.objects.create(name="Nested Auth", description="")
    existing_tag = Tag.objects.create(name="security-tag")

    create_mutation = """
    mutation($input: CreatePostInput!) {
      createPost(input: $input) {
        ok
        object { id }
        errors { field message code }
      }
    }
    """
    denied_create = gql_client.execute(
        create_mutation,
        user=limited_user,
        variables={"input": {"title": "Denied", "category": {"connect": str(category.pk)}}},
    )
    assert denied_create.get("errors") is None
    assert denied_create["data"]["createPost"]["ok"] is False
    assert denied_create["data"]["createPost"]["errors"]

    invalid_shape = gql_client.execute(
        create_mutation,
        variables={
            "input": {
                "title": "Invalid",
                "category": {"connect": str(category.pk)},
                "tags": {
                    "set": [str(existing_tag.pk)],
                    "connect": [str(existing_tag.pk)],
                },
            }
        },
    )
    payload = invalid_shape.get("data", {}).get("createPost")
    assert invalid_shape.get("errors") or (payload and payload.get("errors"))

    created = gql_client.execute(
        create_mutation,
        variables={
            "input": {
                "title": "Allowed",
                "category": {"connect": str(category.pk)},
                "tags": {"connect": [str(existing_tag.pk)]},
            }
        },
    )
    assert created.get("errors") is None
    assert created["data"]["createPost"]["ok"] is True
    post_id = created["data"]["createPost"]["object"]["id"]

    update_mutation = """
    mutation($id: ID!, $input: UpdatePostInput!) {
      updatePost(id: $id, input: $input) {
        ok
        object { id title }
        errors { field message code }
      }
    }
    """
    denied_update = gql_client.execute(
        update_mutation,
        user=limited_user,
        variables={"id": post_id, "input": {"title": "Denied update"}},
    )
    assert denied_update.get("errors") is None
    assert denied_update["data"]["updatePost"]["ok"] is False
    assert denied_update["data"]["updatePost"]["errors"]

    invalid_connect = gql_client.execute(
        update_mutation,
        variables={
            "id": post_id,
            "input": {
                "category": {"connect": "999999"},
            },
        },
    )
    invalid_payload = invalid_connect.get("data", {}).get("updatePost")
    assert invalid_connect.get("errors") or (
        invalid_payload and invalid_payload.get("errors")
    )
