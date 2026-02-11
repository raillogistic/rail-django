"""
Unit tests for multi-tenancy query and mutation scoping.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from rail_django.testing import RailGraphQLTestClient, build_schema
from tests.models import TenantOrganization, TenantProject

pytestmark = pytest.mark.unit


class TestMultiTenancy(TestCase):
    def setUp(self):
        self.org1 = TenantOrganization.objects.create(name="Org 1")
        self.org2 = TenantOrganization.objects.create(name="Org 2")
        self.p1 = TenantProject.objects.create(
            name="Project 1",
            organization=self.org1,
        )
        self.p2 = TenantProject.objects.create(
            name="Project 2",
            organization=self.org2,
        )
        settings = {
            "multitenancy_settings": {
                "enabled": True,
                "tenant_header": "X-Tenant-ID",
                "default_tenant_field": "organization",
                "require_tenant": True,
            },
            "mutation_settings": {
                "generate_bulk": True,
            },
        }
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="tenant_user",
            password="password",
        )
        perms = Permission.objects.filter(
            codename__in=[
                "view_tenantproject",
                "change_tenantproject",
                "add_tenantproject",
            ]
        )
        self.user.user_permissions.add(*perms)
        harness = build_schema(
            schema_name="tenant_test",
            models=["tests.TenantOrganization", "tests.TenantProject"],
            apps=["tests"],
            settings=settings,
        )
        self.schema = harness.schema

    def _client(self, tenant_id=None, user=None):
        headers = {"X-Tenant-ID": str(tenant_id)} if tenant_id else None
        return RailGraphQLTestClient(
            self.schema,
            schema_name="tenant_test",
            user=user or self.user,
            headers=headers,
        )

    def test_list_scoped_by_tenant(self):
        client = self._client(self.org1.id)
        query = """
        query {
            tenantProjectList {
                name
            }
        }
        """
        result = client.execute(query)
        self.assertIsNone(result.get("errors"))
        projects = result["data"]["tenantProjectList"]
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["name"], "Project 1")

    def test_include_filter_respects_tenant(self):
        client = self._client(self.org1.id)
        query = f"""
        query {{
            tenantProjectList(include: ["{self.p2.id}"]) {{
                pk
                name
            }}
        }}
        """
        result = client.execute(query)
        self.assertIsNone(result.get("errors"))
        projects = result["data"]["tenantProjectList"]
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["pk"], str(self.p1.id))

    def test_missing_tenant_rejected(self):
        client = self._client()
        query = """
        query {
            tenantProjectList {
                name
            }
        }
        """
        result = client.execute(query)
        self.assertIsNotNone(result.get("errors"))

    def test_update_cross_tenant_denied(self):
        client = self._client(self.org1.id)
        mutation = f"""
        mutation {{
            updateTenantProject(id: "{self.p2.id}", input: {{ name: "New Name" }}) {{
                ok
                errors {{
                    message
                }}
            }}
        }}
        """
        result = client.execute(mutation)
        data = result["data"]["updateTenantProject"]
        self.assertFalse(data["ok"])
        self.assertTrue(data["errors"])

    def test_bulk_create_mismatched_tenant_rejected(self):
        client = self._client(self.org1.id)
        mutation = f"""
        mutation {{
            bulkCreateTenantProject(inputs: [{{ name: "Bulk Project", organization: {{ connect: "{self.org2.id}" }} }}]) {{
                ok
                errors {{
                    message
                }}
            }}
        }}
        """
        result = client.execute(mutation)
        data = result["data"]["bulkCreateTenantProject"]
        self.assertFalse(data["ok"])
        self.assertTrue(data["errors"])

    def test_bulk_update_mismatched_tenant_rejected(self):
        client = self._client(self.org1.id)
        mutation = f"""
        mutation {{
            bulkUpdateTenantProject(inputs: [{{ id: "{self.p1.id}", data: {{ organization: {{ connect: "{self.org2.id}" }} }} }}]) {{
                ok
                errors {{
                    message
                }}
            }}
        }}
        """
        result = client.execute(mutation)
        data = result["data"]["bulkUpdateTenantProject"]
        self.assertFalse(data["ok"])
        self.assertTrue(data["errors"])

