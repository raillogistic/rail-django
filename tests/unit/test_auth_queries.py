"""
Tests for auth GraphQL queries.
"""

from types import SimpleNamespace

import graphene
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from rail_django.extensions.auth.queries import DummySettingsType, MeQuery, _get_user_settings_type


class AuthRolesQueryTestCase(TestCase):
    """Ensure roles include Django groups and permissions."""

    def test_me_roles_includes_group_permissions(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="role_test",
            email="role_test@example.com",
            password="secret",
        )

        group = Group.objects.create(name="TestGroup")
        permission = Permission.objects.get(codename="add_user")
        group.permissions.add(permission)
        user.groups.add(group)

        schema = graphene.Schema(query=MeQuery)
        query = """
            query {
                me {
                    roles {
                        id
                        name
                        permissions {
                            id
                            name
                            codename
                        }
                    }
                }
            }
        """

        result = schema.execute(query, context_value=SimpleNamespace(user=user))

        self.assertIsNone(result.errors)
        roles = result.data["me"]["roles"]
        self.assertTrue(roles)

        role = next((item for item in roles if item["name"] == "TestGroup"), None)
        self.assertIsNotNone(role)
        self.assertTrue(role["permissions"])

        permission_codenames = {perm["codename"] for perm in role["permissions"]}
        self.assertIn("add_user", permission_codenames)

    def test_user_settings_type_exposes_frontend_contract_fields(self):
        settings_type = _get_user_settings_type()
        if settings_type is None:
            self.skipTest("UserSettings model is not installed in the unit test app set.")
        field_names = set(settings_type._meta.fields.keys())
        self.assertIn("id", field_names)
        self.assertIn("table_configs", field_names)

    def test_dummy_settings_type_matches_frontend_contract_fields(self):
        field_names = set(DummySettingsType._meta.fields.keys())

        self.assertIn("id", field_names)
        self.assertIn("table_configs", field_names)
