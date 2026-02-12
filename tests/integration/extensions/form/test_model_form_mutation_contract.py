import pytest
from graphql import GraphQLError

from rail_django.extensions.form.normalization.input_normalizer import (
    enforce_primary_key_only_update_target,
)
from rail_django.extensions.form.normalization.relation_policy import (
    enforce_action_allowed,
    is_action_allowed,
)
from rail_django.extensions.form.schema.mutations import (
    build_conflict_outcome,
    detect_stale_update_conflict,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_primary_key_only_update_target_and_stale_conflict_response():
    assert enforce_primary_key_only_update_target({"id": "123"}) == "123"

    with pytest.raises(GraphQLError):
        enforce_primary_key_only_update_target({"slug": "not-allowed"})

    assert detect_stale_update_conflict(current_version=2, submitted_version=1) is True
    outcome = build_conflict_outcome()
    assert outcome["ok"] is False
    assert outcome["conflict"] is True
    assert outcome["errors"][0]["code"] == "CONFLICT"


def test_nested_relation_policy_default_allow_and_path_level_block():
    relation_policies = {
        "tags": {"default_allow": True, "blocked": ["DELETE"]},
        "comments": {"default_allow": False, "allowed": ["CREATE", "CONNECT"]},
    }

    assert is_action_allowed(relation_policies, path="tags", action="connect") is True
    assert is_action_allowed(relation_policies, path="tags", action="delete") is False
    assert is_action_allowed(relation_policies, path="comments", action="create") is True
    assert is_action_allowed(relation_policies, path="comments", action="update") is False

    with pytest.raises(GraphQLError):
        enforce_action_allowed(relation_policies, path="comments", action="update")
