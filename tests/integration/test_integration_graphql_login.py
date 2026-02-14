import logging
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from tests.integration.test_helpers_graphql_endpoint import (
    LOGIN_MUTATION,
    VIEWER_QUERY,
    graphql_post,
    login_and_get_token,
)

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

TEST_GRAPHQL_SCHEMAS_AUTH_REQUIRED = {
    "gql": {
        "apps": ["test_app"],
        "schema_settings": {
            "authentication_required": True,
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
def test_login_mutation_valid_and_invalid_credentials(client):
    User = get_user_model()
    User.objects.create_user(
        username="integration_login_user",
        password="integration_pass_123",
    )

    _, valid_payload = graphql_post(
        client,
        query=LOGIN_MUTATION,
        variables={
            "username": "integration_login_user",
            "password": "integration_pass_123",
        },
    )
    valid_login = valid_payload.get("data", {}).get("login") or {}
    assert valid_login.get("ok") is True
    assert isinstance(valid_login.get("token"), str)
    assert valid_login.get("token")

    _, invalid_payload = graphql_post(
        client,
        query=LOGIN_MUTATION,
        variables={
            "username": "integration_login_user",
            "password": "wrong_password",
        },
    )
    invalid_login = invalid_payload.get("data", {}).get("login") or {}
    assert invalid_login.get("ok") is False
    assert invalid_login.get("token") in (None, "")
    assert invalid_login.get("errors")


@override_settings(
    ROOT_URLCONF="rail_django.urls",
    ENVIRONMENT="development",
    RAIL_DJANGO_ENABLE_TEST_GRAPHQL_ENDPOINT=True,
    RAIL_DJANGO_GRAPHQL_SCHEMAS=TEST_GRAPHQL_SCHEMAS_AUTH_REQUIRED,
)
def test_login_mutation_is_accessible_on_open_test_endpoint_even_when_schema_requires_auth(
    client,
):
    User = get_user_model()
    User.objects.create_user(
        username="integration_login_open_endpoint_user",
        password="integration_open_endpoint_pass",
    )

    _, payload = graphql_post(
        client,
        query=LOGIN_MUTATION,
        variables={
            "username": "integration_login_open_endpoint_user",
            "password": "integration_open_endpoint_pass",
        },
    )
    login_payload = payload.get("data", {}).get("login") or {}
    assert login_payload.get("ok") is True
    assert isinstance(login_payload.get("token"), str)
    assert login_payload.get("token")


@override_settings(
    ROOT_URLCONF="rail_django.urls",
    ENVIRONMENT="development",
    RAIL_DJANGO_ENABLE_TEST_GRAPHQL_ENDPOINT=True,
    RAIL_DJANGO_GRAPHQL_SCHEMAS=TEST_GRAPHQL_SCHEMAS,
)
def test_viewer_query_returns_authenticated_user(client):
    User = get_user_model()
    User.objects.create_user(
        username="integration_viewer_user",
        password="integration_viewer_pass",
    )

    token = login_and_get_token(
        client,
        username="integration_viewer_user",
        password="integration_viewer_pass",
    )
    assert token

    _, viewer_payload = graphql_post(client, query=VIEWER_QUERY, token=token)
    viewer = viewer_payload.get("data", {}).get("viewer")
    assert viewer is not None
    assert viewer["username"] == "integration_viewer_user"


@override_settings(
    ROOT_URLCONF="rail_django.urls",
    ENVIRONMENT="development",
    RAIL_DJANGO_ENABLE_TEST_GRAPHQL_ENDPOINT=True,
    RAIL_DJANGO_GRAPHQL_SCHEMAS=TEST_GRAPHQL_SCHEMAS,
)
def test_login_error_logs_redact_sensitive_values(client, caplog):
    User = get_user_model()
    User.objects.create_user(
        username="integration_redaction_user",
        password="integration_redaction_pass",
    )

    with patch(
        "rail_django.extensions.auth.mutations.authenticate",
        side_effect=RuntimeError("token=super-secret password=my-secret-pass"),
    ):
        with caplog.at_level(logging.ERROR):
            _, payload = graphql_post(
                client,
                query=LOGIN_MUTATION,
                variables={
                    "username": "integration_redaction_user",
                    "password": "integration_redaction_pass",
                },
            )

    login_payload = payload.get("data", {}).get("login") or {}
    assert login_payload.get("ok") is False

    collected_logs = " ".join(caplog.messages)
    assert "super-secret" not in collected_logs
    assert "my-secret-pass" not in collected_logs
    assert "[REDACTED]" in collected_logs
