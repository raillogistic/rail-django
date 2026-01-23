"""
Integration tests for filtering, pagination, and mutation workflows.
"""

import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Category, Client, Comment, Post

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    harness = build_schema(schema_name="test", apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_superuser(
        username="graphql_admin",
        email="graphql_admin@example.com",
        password="pass12345",
    )
    return RailGraphQLTestClient(harness.schema, schema_name="test", user=user)


def _create_category(name="General"):
    return Category.objects.create(name=name, description="")


def test_posts_query_requires_model_permission(gql_client):
    category = _create_category()
    Post.objects.create(title="Restricted Post", category=category)

    User = get_user_model()
    user = User.objects.create_user(username="no_perm_user", password="pass12345")

    query = """
    query {
        posts {
            title
        }
    }
    """
    result = gql_client.execute(query, user=user)
    errors = result.get("errors") or []
    assert errors
    first_error = errors[0]
    message = (
        first_error.get("message", "")
        if isinstance(first_error, dict)
        else str(first_error)
    )
    assert "permission" in message.lower()
    assert "test_app.view_post" in message


def test_simple_quick_filter(gql_client):
    category = _create_category()
    Post.objects.create(title="Alpha Post", category=category)
    Post.objects.create(title="Beta Post", category=category)

    query = """
    query($quick: String) {
        posts(quick: $quick) {
            title
        }
    }
    """
    result = gql_client.execute(query, variables={"quick": "Alpha"})
    assert result.get("errors") is None
    titles = [item["title"] for item in result["data"]["posts"]]
    assert titles == ["Alpha Post"]


def test_nested_filters_and_or_not(gql_client):
    category = _create_category()
    Post.objects.create(title="Alpha", category=category)
    Post.objects.create(title="Beta", category=category)
    Post.objects.create(title="Gamma", category=category)

    query = """
    query($where: PostWhereInput) {
        posts(where: $where, orderBy: ["title"]) {
            title
        }
    }
    """
    variables = {
        "where": {
            "OR": [
                {"title": {"eq": "Alpha"}},
                {"title": {"eq": "Beta"}}
            ],
            "NOT": {"title": {"eq": "Gamma"}},
        }
    }
    result = gql_client.execute(query, variables=variables)
    assert result.get("errors") is None
    titles = [item["title"] for item in result["data"]["posts"]]
    assert titles == ["Alpha", "Beta"]


def test_paginated_query_returns_page_info(gql_client):
    category = _create_category()
    for i in range(5):
        Post.objects.create(title=f"Post {i}", category=category)

    query = """
    query {
        postPages(page: 2, perPage: 2, orderBy: ["title"]) {
            items {
                title
            }
            pageInfo {
                totalCount
                pageCount
                currentPage
                perPage
                hasNextPage
                hasPreviousPage
            }
        }
    }
    """
    result = gql_client.execute(query)
    assert result.get("errors") is None

    page = result["data"]["postPages"]
    assert len(page["items"]) == 2
    assert page["pageInfo"]["totalCount"] == 5
    assert page["pageInfo"]["pageCount"] == 3
    assert page["pageInfo"]["currentPage"] == 2
    assert page["pageInfo"]["perPage"] == 2
    assert page["pageInfo"]["hasPreviousPage"] is True
    assert page["pageInfo"]["hasNextPage"] is True


def test_offset_limit_pagination(gql_client):
    category = _create_category()
    Post.objects.create(title="A", category=category)
    Post.objects.create(title="B", category=category)
    Post.objects.create(title="C", category=category)
    Post.objects.create(title="D", category=category)

    query = """
    query {
        posts(offset: 1, limit: 2, orderBy: ["title"]) {
            title
        }
    }
    """
    result = gql_client.execute(query)
    assert result.get("errors") is None
    titles = [item["title"] for item in result["data"]["posts"]]
    assert titles == ["B", "C"]


def test_mutation_crud_cycle(gql_client):
    category = _create_category()

    create_mutation = """
    mutation($input: CreatePostInput!) {
        createPost(input: $input) {
            ok
            object {
                id
                title
            }
            errors {
                field
                message
            }
        }
    }
    """
    create_input = {"title": "First Post", "category": {"connect": str(category.id)}}
    create_result = gql_client.execute(create_mutation, variables={"input": create_input})
    assert create_result.get("errors") is None

    payload = create_result["data"]["createPost"]
    assert payload["ok"] is True
    post_id = payload["object"]["id"]

    update_mutation = """
    mutation($id: ID!, $input: UpdatePostInput!) {
        updatePost(id: $id, input: $input) {
            ok
            object {
                id
                title
            }
            errors {
                field
                message
            }
        }
    }
    """
    update_result = gql_client.execute(
        update_mutation,
        variables={"id": post_id, "input": {"title": "Updated Post"}},
    )
    assert update_result.get("errors") is None
    assert update_result["data"]["updatePost"]["object"]["title"] == "Updated Post"

    delete_mutation = """
    mutation($id: ID!) {
        deletePost(id: $id) {
            ok
            errors {
                field
                message
            }
        }
    }
    """
    delete_result = gql_client.execute(delete_mutation, variables={"id": post_id})
    assert delete_result.get("errors") is None
    assert delete_result["data"]["deletePost"]["ok"] is True
    assert Post.objects.filter(id=post_id).exists() is False


def test_mutation_nested_create_with_tags_and_comments(gql_client):
    category = _create_category()

    mutation = """
    mutation($input: CreatePostInput!) {
        createPost(input: $input) {
            ok
            object {
                id
                title
                tags {
                    name
                }
                comments {
                    content
                }
            }
            errors {
                field
                message
            }
        }
    }
    """
    variables = {
        "input": {
            "title": "Nested Post",
            "category": {"connect": str(category.id)},
            "tags": {"create": [{"name": "django"}, {"name": "graphql"}]},
            "comments": {"create": [{"content": "First"}, {"content": "Second"}]},
        }
    }
    result = gql_client.execute(mutation, variables=variables)
    assert result.get("errors") is None

    payload = result["data"]["createPost"]
    assert payload["ok"] is True
    assert len(payload["object"]["tags"]) == 2
    assert Comment.objects.filter(post_id=payload["object"]["id"]).count() == 2


def test_mutation_duplicate_unique_error(gql_client):
    mutation = """
    mutation($input: CreateClientInput!) {
        createClient(input: $input) {
            ok
            object {
                id
            }
            errors {
                field
                message
            }
        }
    }
    """
    data = {"name": "Alice", "email": "alice@example.com"}
    first = gql_client.execute(mutation, variables={"input": data})
    assert first.get("errors") is None
    assert first["data"]["createClient"]["ok"] is True

    second = gql_client.execute(mutation, variables={"input": data})
    assert second.get("errors") is None
    assert second["data"]["createClient"]["ok"] is False
    assert second["data"]["createClient"]["errors"]


def test_mutation_dual_field_conflict_returns_error(gql_client):
    category = _create_category()

    mutation = """
    mutation($input: CreatePostInput!) {
        createPost(input: $input) {
            ok
            object {
                id
            }
            errors {
                field
                message
            }
        }
    }
    """
    variables = {
        "input": {
            "title": "Conflict Post",
            "category": {"connect": str(category.id), "create": {"name": "Nested"}},
        }
    }
    result = gql_client.execute(mutation, variables=variables)
    assert result.get("errors") is None
    assert result["data"]["createPost"]["ok"] is False
    assert result["data"]["createPost"]["errors"]

