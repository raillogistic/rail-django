import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from rail_django.extensions.auth import JWTManager
from test_app.models import Category, Post, Tag
from tests.integration.test_helpers_graphql_endpoint import graphql_post

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

TEST_GRAPHQL_SCHEMAS = {
    "gql": {
        "apps": ["test_app"],
        "schema_settings": {
            "authentication_required": False,
            "enable_graphiql": False,
        },
    }
}


@override_settings(
    ROOT_URLCONF="rail_django.urls",
    ENVIRONMENT="development",
    RAIL_DJANGO_ENABLE_TEST_GRAPHQL_ENDPOINT=True,
    RAIL_DJANGO_GRAPHQL_SCHEMAS=TEST_GRAPHQL_SCHEMAS,
)
def test_dedicated_test_endpoint_supports_graphql_crud_regression_paths(client):
    from rail_django.core.registry import schema_registry

    schema_registry.clear()
    User = get_user_model()
    admin = User.objects.create_superuser(
        username="endpoint_admin",
        email="endpoint_admin@example.com",
        password="endpoint_admin_pass",
    )
    limited = User.objects.create_user(
        username="endpoint_limited",
        password="endpoint_limited_pass",
    )

    admin_token = JWTManager.generate_token(admin)["token"]
    limited_token = JWTManager.generate_token(limited)["token"]
    assert admin_token
    assert limited_token

    category = Category.objects.create(name="Integration Category", description="")
    existing_tag = Tag.objects.create(name="endpoint-existing-tag")
    Post.objects.create(title="Seed Post", category=category)

    page_query = """
    query {
      postPage(page: 1, perPage: 20) {
        pageInfo { totalCount }
      }
    }
    """
    _, denied_page = graphql_post(client, query=page_query, token=limited_token)
    assert denied_page.get("errors") or (
        denied_page.get("data", {}).get("postPage") in (None, {})
    )

    _, allowed_page = graphql_post(client, query=page_query, token=admin_token)
    assert allowed_page.get("errors") is None
    assert allowed_page["data"]["postPage"]["pageInfo"]["totalCount"] >= 1

    create_mutation = """
    mutation($input: CreatePostInput!) {
      createPost(input: $input) {
        ok
        object { id title }
        errors { field message code }
      }
    }
    """
    _, create_payload = graphql_post(
        client,
        token=admin_token,
        query=create_mutation,
        variables={
            "input": {
                "title": "Endpoint Created Post",
                "category": {"connect": str(category.pk)},
                "tags": {"connect": [str(existing_tag.pk)]},
            }
        },
    )
    assert create_payload.get("errors") is None
    create_result = create_payload["data"]["createPost"]
    assert create_result["ok"] is True
    post_id = create_result["object"]["id"]

    update_mutation = """
    mutation($id: ID!, $input: UpdatePostInput!) {
      updatePost(id: $id, input: $input) {
        ok
        object { id title }
        errors { field message code }
      }
    }
    """
    _, denied_update = graphql_post(
        client,
        token=limited_token,
        query=update_mutation,
        variables={"id": post_id, "input": {"title": "Denied Title"}},
    )
    denied_update_payload = denied_update.get("data", {}).get("updatePost") or {}
    assert denied_update.get("errors") or denied_update_payload.get("ok") is False

    _, allowed_update = graphql_post(
        client,
        token=admin_token,
        query=update_mutation,
        variables={"id": post_id, "input": {"title": "Updated Title"}},
    )
    assert allowed_update.get("errors") is None
    assert allowed_update["data"]["updatePost"]["ok"] is True

    delete_mutation = """
    mutation($id: ID!) {
      deletePost(id: $id) {
        ok
        errors { field message code }
      }
    }
    """
    _, denied_delete = graphql_post(
        client,
        token=limited_token,
        query=delete_mutation,
        variables={"id": post_id},
    )
    denied_delete_payload = denied_delete.get("data", {}).get("deletePost") or {}
    assert denied_delete.get("errors") or denied_delete_payload.get("ok") is False

    _, allowed_delete = graphql_post(
        client,
        token=admin_token,
        query=delete_mutation,
        variables={"id": post_id},
    )
    assert allowed_delete.get("errors") is None
    assert allowed_delete["data"]["deletePost"]["ok"] is True
