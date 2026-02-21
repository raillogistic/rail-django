"""Integration tests for ABAC behavior through GraphQL permission APIs."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from rail_django.config_proxy import clear_runtime_settings, configure_schema_settings
from rail_django.security.abac import ABACPolicy, ConditionOperator, MatchCondition, abac_engine
from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client_abac():
    schema_name = "test_abac_graphql"
    configure_schema_settings(
        schema_name,
        clear_existing=True,
        security_settings={
            "enable_abac": True,
            "hybrid_strategy": "rbac_and_abac",
            "abac_default_effect": "deny",
        },
    )

    abac_engine.clear_policies()
    abac_engine.register_policy(
        ABACPolicy(
            name="deny_authenticated_for_test",
            effect="deny",
            subject_conditions={
                "authenticated": MatchCondition(ConditionOperator.EQ, value=True)
            },
        )
    )

    harness = build_schema(schema_name=schema_name, apps=["test_app"])
    User = get_user_model()
    user = User.objects.create_user(
        username="abac_user",
        email="abac@example.com",
        password="pass12345",
    )

    content_type = ContentType.objects.get_for_model(Product)
    permission = Permission.objects.get(
        content_type=content_type,
        codename="view_product",
    )
    user.user_permissions.add(permission)

    client = RailGraphQLTestClient(harness.schema, schema_name=schema_name, user=user)
    try:
        yield client
    finally:
        abac_engine.clear_policies()
        clear_runtime_settings(schema_name=schema_name)


def test_explain_permission_reports_abac_denial(gql_client_abac):
    query = """
    query {
      explainPermission(
        permission: "test_app.view_product",
        modelName: "test_app.Product",
        operation: "read"
      ) {
        allowed
        reason
        rbacAllowed
        abacAllowed
        abacReason
        hybridStrategy
      }
    }
    """
    result = gql_client_abac.execute(query)
    assert result.get("errors") is None
    explanation = result["data"]["explainPermission"]
    assert explanation["rbacAllowed"] is True
    assert explanation["abacAllowed"] is False
    assert explanation["allowed"] is False
    assert explanation["hybridStrategy"] == "rbac_and_abac"

