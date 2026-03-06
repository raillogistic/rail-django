import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from rail_django.security.frontend_routes import (
    FrontendRouteAccessRule,
    frontend_route_access_registry,
    load_frontend_route_access_from_payload,
)
from rail_django.security.rbac import RoleDefinition, RoleType, role_manager

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def clear_frontend_route_access_registry():
    frontend_route_access_registry.clear()
    yield
    frontend_route_access_registry.clear()


def test_frontend_route_access_registry_evaluates_role_and_permission_requirements():
    role_name = "frontend_routes_dispatcher"
    role_manager.register_role(
        RoleDefinition(
            name=role_name,
            description="Dispatch operations routes",
            role_type=RoleType.BUSINESS,
            permissions=["operations.view_orders"],
        )
    )

    user = get_user_model().objects.create_user(
        username="frontend_routes_allowed",
        password="pass12345",
    )
    group, _ = Group.objects.get_or_create(name=role_name)
    user.groups.add(group)

    frontend_route_access_registry.register(
        FrontendRouteAccessRule(
            target_type="route",
            target="/operations/orders",
            any_roles=(role_name,),
            all_permissions=("operations.view_orders",),
        )
    )

    snapshot = frontend_route_access_registry.snapshot_for_user(user)
    assert len(snapshot) == 1
    assert snapshot[0]["allowed"] is True
    assert snapshot[0]["denial_reason"] is None


def test_frontend_route_access_requires_auth_for_permission_guarded_public_rule():
    allowed, denial_reason = frontend_route_access_registry.evaluate(
        None,
        FrontendRouteAccessRule(
            target_type="route",
            target="/operations/orders",
            require_authentication=False,
            any_permissions=("operations.view_orders",),
        ),
    )

    assert allowed is False
    assert denial_reason == "Authentication required for permission-based access"


def test_load_frontend_route_access_from_payload_registers_camel_case_rules():
    count = load_frontend_route_access_from_payload(
        {
            "frontend_route_access": [
                {
                    "targetType": "navigation-group",
                    "target": "operations-group",
                    "anyRoles": ["ops_manager"],
                }
            ]
        },
        source="meta.json",
    )

    assert count == 1
    rules = frontend_route_access_registry.get_rules()
    assert len(rules) == 1
    assert rules[0].target_type == "navigation-group"
    assert rules[0].target == "operations-group"
    assert rules[0].any_roles == ("ops_manager",)
