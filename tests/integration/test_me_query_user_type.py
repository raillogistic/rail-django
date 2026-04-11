import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

from rail_django.testing import RailGraphQLTestClient, build_schema
from test_app.models import Profile

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_me_uses_project_user_type_with_auth_fields():
    schema_name = "test_me_project_user_type"
    harness = build_schema(schema_name=schema_name, apps=["test_app"])

    User = get_user_model()
    user = User.objects.create_user(
        username="me_user",
        email="me_user@example.com",
        password="pass12345",
        first_name="Ada",
        last_name="Lovelace",
    )
    Profile.objects.create(user=user, bio="Project profile relation")

    group = Group.objects.create(name="MeGroup")
    permission = Permission.objects.get(codename="add_user")
    group.permissions.add(permission)
    user.groups.add(group)

    client = RailGraphQLTestClient(harness.schema, schema_name=schema_name, user=user)
    result = client.execute(
        """
        query {
          me {
            username
            profile {
              bio
            }
            roles {
              name
            }
          }
        }
        """
    )

    assert result.get("errors") is None
    me = result["data"]["me"]
    assert me["username"] == "me_user"
    assert me["profile"]["bio"] == "Project profile relation"
    assert [role["name"] for role in me["roles"]] == ["MeGroup"]
