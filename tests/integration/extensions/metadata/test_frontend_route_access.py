import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from rail_django.security.frontend_routes import frontend_route_access_registry
from rail_django.security.rbac import RoleDefinition, RoleType, role_manager
from rail_django.testing import RailGraphQLTestClient, build_schema

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

FRONTEND_ROUTE_ACCESS_QUERY = """
query FrontendRouteAccess {
  frontendRouteAccess {
    version
    rules {
      targetType
      target
      requireAuthentication
      anyPermissions
      allPermissions
      anyRoles
      allRoles
      allowed
      denialReason
    }
  }
}
"""


@pytest.fixture(autouse=True)
def clear_frontend_route_access_registry():
    frontend_route_access_registry.clear()
    yield
    frontend_route_access_registry.clear()


def test_frontend_route_access_query_returns_resolved_rule_snapshot():
    role_name = "metadata_ops_manager"
    role_manager.register_role(
        RoleDefinition(
            name=role_name,
            description="Metadata route access test role",
            role_type=RoleType.BUSINESS,
            permissions=["operations.view_orders"],
        )
    )
    frontend_route_access_registry.register_many(
        [
            {
                "targetType": "route",
                "target": "/operations/orders",
                "anyRoles": [role_name],
            },
            {
                "targetType": "route",
                "target": "/operations/shipments",
                "allPermissions": ["operations.view_shipments"],
            },
        ]
    )

    harness = build_schema(
        schema_name="test_frontend_route_access",
        apps=["test_app"],
    )
    user = get_user_model().objects.create_user(
        username="metadata_frontend_route_user",
        password="pass12345",
    )
    group, _ = Group.objects.get_or_create(name=role_name)
    user.groups.add(group)

    client = RailGraphQLTestClient(
        harness.schema,
        schema_name="test_frontend_route_access",
        user=user,
    )
    payload = client.execute(FRONTEND_ROUTE_ACCESS_QUERY)

    assert payload.get("errors") is None
    manifest = payload["data"]["frontendRouteAccess"]
    assert manifest["version"]

    rules = {rule["target"]: rule for rule in manifest["rules"]}
    assert rules["/operations/orders"]["allowed"] is True
    assert rules["/operations/orders"]["anyRoles"] == [role_name]
    assert rules["/operations/shipments"]["allowed"] is False
    assert rules["/operations/shipments"]["denialReason"] == (
        "Permission required: operations.view_shipments"
    )
