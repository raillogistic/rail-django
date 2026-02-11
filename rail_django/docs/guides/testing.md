# Testing Guide

This guide covers best practices and utilities for testing GraphQL APIs built with Rail Django. The framework provides specialized tools to simplify schema generation and execution of GraphQL operations in a test environment.

## Overview

Testing a Rail Django application typically involves:
1. **Unit Testing**: Testing individual components like custom resolvers or utility functions.
2. **Integration Testing**: Testing the full GraphQL execution flow, including permissions, filters, and database interactions.

We recommend using [pytest](https://docs.pytest.org/) along with [pytest-django](https://pytest-django.readthedocs.io/).

!!! tip "Database Access"
    For any test that interacts with the Django database (most integration tests), ensure you use the `@pytest.mark.django_db` decorator or the `db` fixture.

## Key Testing Utilities

The framework provides helpers in `rail_django.testing` (specifically in `harness.py`).

### RailGraphQLTestClient

The `RailGraphQLTestClient` is the primary tool for executing GraphQL operations. It simulates a real Django request, ensuring that middleware and context are correctly initialized.

- **Initialization**: `RailGraphQLTestClient(schema, schema_name="default", user=None, headers=None)`
- **Execution**: `client.execute(query, variables=None, user=None, headers=None)`

**Key Feature**: It automatically attaches the `user` and `schema_name` to the request, which is critical for testing security policies and multitenancy.

### build_schema

The `build_schema` helper allows you to dynamically generate a Graphene schema for tests without needing a full Django setup or a pre-defined registry.

- **Usage**: `harness = build_schema(schema_name="test", apps=["my_app"])`
- **Returns**: A `SchemaHarness` object containing the `schema`, `builder`, and `registry`.

This is particularly useful for isolating tests to specific apps or models.

### override_rail_settings

A context manager and decorator to temporarily override framework-specific settings during a test.

```python
from rail_django.testing import override_rail_settings

def test_custom_behavior():
    with override_rail_settings(schema_settings={"auto_camelcase": False}):
        # Run tests with camelCase disabled
        ...
```

## Common Testing Patterns

### Setting up a Test Client

Using a pytest fixture is the most efficient way to manage test clients.

```python
import pytest
from rail_django.testing import RailGraphQLTestClient, build_schema
from django.contrib.auth import get_user_model

User = get_user_model()

@pytest.fixture
def gql_client(db):
    # Build a schema for the specific app
    harness = build_schema(schema_name="test", apps=["test_app"])

    # Create a user for authenticated requests
    user = User.objects.create_superuser(username="admin", password="password")

    return RailGraphQLTestClient(harness.schema, user=user)
```

### Testing Queries

When testing queries, assert the absence of errors and verify the returned data structure.

```python
@pytest.mark.django_db
def test_query_posts(gql_client):
    query = """
    query {
        postList {
            title
        }
    }
    """
    result = gql_client.execute(query)

    assert result.get("errors") is None
    assert "postList" in result["data"]
    assert isinstance(result["data"]["postList"], list)
```

### Testing Mutations

For mutations, verify the `ok` status, the returned object data, and any validation errors.

```python
@pytest.mark.django_db
def test_create_post(gql_client):
    mutation = """
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
    variables = {"input": {"title": "New Post"}}
    result = gql_client.execute(mutation, variables=variables)

    assert result.get("errors") is None
    payload = result["data"]["createPost"]
    assert payload["ok"] is True
    assert payload["object"]["title"] == "New Post"
```

### Testing Permissions

You can test restricted access by overriding the user in the `execute` method.

```python
from django.contrib.auth.models import AnonymousUser

@pytest.mark.django_db
def test_restricted_access(gql_client):
    # Test as an anonymous user
    anonymous_user = AnonymousUser()
    query = "{ secretData { id } }"

    result = gql_client.execute(query, user=anonymous_user)

    assert "errors" in result
    # Verify the error message contains 'permission' (case-insensitive)
    assert "permission" in result["errors"][0]["message"].lower()
```

### Testing Filtering

Rail Django's advanced filtering can be tested by passing variables to the `where` argument.

```python
@pytest.mark.django_db
def test_filtering(gql_client):
    query = """
    query($where: PostWhereInput) {
        postList(where: $where) {
            title
        }
    }
    """
    variables = {
        "where": {
            "title": {"icontains": "django"}
        }
    }
    result = gql_client.execute(query, variables=variables)

    assert result.get("errors") is None
    # Add assertions for filtered results
```
