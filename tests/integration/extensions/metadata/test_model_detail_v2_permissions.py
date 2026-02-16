import pytest
from django.contrib.auth import get_user_model

from rail_django.testing import RailGraphQLTestClient, build_schema

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def gql_client():
    harness = build_schema(schema_name="test_detail_v2_permissions", apps=["test_app"])
    User = get_user_model()
    admin = User.objects.create_superuser(
        username="detail_permissions_admin",
        email="detail_permissions_admin@example.com",
        password="pass12345",
    )
    return RailGraphQLTestClient(
        harness.schema,
        schema_name="test_detail_v2_permissions",
        user=admin,
    )


def test_detail_permissions_fail_closed_on_conflicting_read_signals(gql_client, monkeypatch):
    from rail_django.extensions.metadata.permissions_extractor import PermissionExtractorMixin

    def _conflicting_permissions(_self, _model, _user):
        return {
            "can_list": False,
            "can_retrieve": True,
            "can_create": True,
            "can_update": True,
            "can_delete": True,
            "can_bulk_create": True,
            "can_bulk_update": True,
            "can_bulk_delete": True,
            "can_export": True,
            "denial_reasons": {},
        }

    monkeypatch.setattr(
        PermissionExtractorMixin,
        "_extract_permissions",
        _conflicting_permissions,
    )

    query = """
    query($input: DetailContractInputType!) {
      modelDetailContract(input: $input) {
        ok
        reason
        contract {
          modelName
          permissions {
            modelReadable
          }
        }
      }
    }
    """
    payload = gql_client.execute(
        query,
        variables={"input": {"app": "test_app", "model": "Product"}},
    )

    assert payload.get("errors") is None
    result = payload["data"]["modelDetailContract"]
    assert result["ok"] is False
    assert result["reason"] == "Access denied"
    assert result["contract"]["permissions"]["modelReadable"] is False
