import json
from typing import Any

from django.test import Client


DEFAULT_TEST_GRAPHQL_ENDPOINT = "/graphql-test/"

LOGIN_MUTATION = """
mutation Login($username: String!, $password: String!) {
  login(username: $username, password: $password) {
    ok
    token
    errors
  }
}
"""

VIEWER_QUERY = """
query Viewer {
  viewer {
    id
    username
  }
}
"""


def graphql_test_endpoint(schema_name: str = "gql") -> str:
    if schema_name == "gql":
        return DEFAULT_TEST_GRAPHQL_ENDPOINT
    return f"{DEFAULT_TEST_GRAPHQL_ENDPOINT}{schema_name}/"


def graphql_post(
    client: Client,
    *,
    query: str,
    variables: dict[str, Any] | None = None,
    token: str | None = None,
    schema_name: str = "gql",
) -> tuple[Any, dict[str, Any]]:
    endpoint = graphql_test_endpoint(schema_name=schema_name)
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables
    headers: dict[str, str] = {}
    if token:
        headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    response = client.post(
        endpoint,
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )
    body = json.loads(response.content.decode("utf-8"))
    return response, body


def login_and_get_token(client: Client, *, username: str, password: str) -> str | None:
    _, payload = graphql_post(
        client,
        query=LOGIN_MUTATION,
        variables={"username": username, "password": password},
    )
    login_payload = payload.get("data", {}).get("login") or {}
    return login_payload.get("token")
