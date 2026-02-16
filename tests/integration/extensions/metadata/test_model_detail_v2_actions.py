import pytest
from django.contrib.auth import get_user_model

from rail_django.extensions.metadata.detail_actions import execute_detail_action
from rail_django.extensions.metadata.extractor import ModelSchemaExtractor

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def users():
    User = get_user_model()
    admin = User.objects.create_superuser(
        username="detail_actions_admin",
        email="detail_actions_admin@example.com",
        password="pass12345",
    )
    limited = User.objects.create_user(
        username="detail_actions_limited",
        password="pass12345",
    )
    return admin, limited


def _extract_action_definitions(user, *, object_id: str):
    extractor = ModelSchemaExtractor(schema_name="test_detail_v2_actions")
    schema_payload = extractor.extract("test_app", "Product", user=user, object_id=object_id)
    actions = [
        {
            "key": action["name"],
            "label": action["name"],
            "scope": "MODEL",
            "mutation_name": action["name"],
            "input_template": {"id": "{{record.id}}"},
            "permission_key": "",
            "audit_enabled": True,
            "allowed": bool(action.get("allowed", False)),
            "reason": action.get("reason"),
        }
        for action in (schema_payload.get("mutations") or [])
        if str(action.get("operation") or "").lower() not in {"list", "retrieve"}
    ]
    available = [str(entry.get("name")) for entry in (schema_payload.get("mutations") or [])]
    return actions, available


def test_detail_action_execution_emits_audit_for_allowed_and_denied_paths(users):
    admin, limited = users
    record_id = "42"

    admin_actions, admin_available_mutations = _extract_action_definitions(
        admin,
        object_id=record_id,
    )
    limited_actions, limited_available_mutations = _extract_action_definitions(
        limited,
        object_id=record_id,
    )

    if not admin_actions:
        admin_actions = [
            {
                "key": "deleteProduct",
                "label": "deleteProduct",
                "scope": "MODEL",
                "mutation_name": "deleteProduct",
                "input_template": {"id": "{{record.id}}"},
                "permission_key": "",
                "audit_enabled": True,
                "allowed": True,
                "reason": None,
            }
        ]
    if not limited_actions:
        limited_actions = [
            {
                "key": "deleteProduct",
                "label": "deleteProduct",
                "scope": "MODEL",
                "mutation_name": "deleteProduct",
                "input_template": {"id": "{{record.id}}"},
                "permission_key": "",
                "audit_enabled": True,
                "allowed": False,
                "reason": "Action denied",
            }
        ]
    if not admin_available_mutations:
        admin_available_mutations = ["deleteProduct"]
    if not limited_available_mutations:
        limited_available_mutations = ["deleteProduct"]

    if admin_actions and not any(action["allowed"] for action in admin_actions):
        admin_actions = [
            {
                **admin_actions[0],
                "allowed": True,
                "reason": None,
            },
            *admin_actions[1:],
        ]
    if limited_actions and all(action["allowed"] for action in limited_actions):
        limited_actions = [
            {
                **limited_actions[0],
                "allowed": False,
                "reason": "Action denied",
            },
            *limited_actions[1:],
        ]

    allowed_action = next((action for action in admin_actions if action["allowed"]), None)
    denied_action = next((action for action in limited_actions if not action["allowed"]), None)

    assert allowed_action is not None
    assert denied_action is not None

    sink_events = []
    allowed_result = execute_detail_action(
        admin_actions,
        action_key=allowed_action["key"],
        context={"record": {"id": record_id}},
        model_name="Product",
        record_id=record_id,
        actor_id=str(admin.pk),
        available_mutations=admin_available_mutations,
        execute=lambda _name, _payload: {"ok": True},
        sink=sink_events.append,
    )
    assert allowed_result["ok"] is True
    assert allowed_result["denied"] is False
    assert allowed_result["outcome"] == "ALLOWED_SUCCESS"
    assert allowed_result["mutation_name"] == allowed_action["mutation_name"]
    assert allowed_result["payload"]["id"] == record_id

    denied_result = execute_detail_action(
        limited_actions,
        action_key=denied_action["key"],
        context={"record": {"id": record_id}},
        model_name="Product",
        record_id=record_id,
        actor_id=str(limited.pk),
        available_mutations=limited_available_mutations,
        execute=lambda _name, _payload: {"ok": True},
        sink=sink_events.append,
    )
    assert denied_result["ok"] is False
    assert denied_result["denied"] is True
    assert denied_result["outcome"] == "DENIED"
    assert denied_result["mutation_name"] is None

    outcomes = [event["outcome"] for event in sink_events]
    assert "ALLOWED_SUCCESS" in outcomes
    assert "DENIED" in outcomes
