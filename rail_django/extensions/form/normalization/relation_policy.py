"""
Nested relation action policy helpers for generated form mutations.
"""

from __future__ import annotations

from typing import Any

from graphql import GraphQLError

from ..utils.pathing import normalize_path

DEFAULT_ACTIONS = (
    "connect",
    "create",
    "update",
    "disconnect",
    "delete",
    "set",
    "clear",
)


def resolve_relation_policy(
    relation_policies: dict[str, Any] | None,
    path: str,
) -> dict[str, Any]:
    relation_policies = relation_policies or {}
    normalized = normalize_path(path)
    if not normalized:
        return {}
    return relation_policies.get(normalized) or relation_policies.get(path) or {}


def is_action_allowed(
    relation_policies: dict[str, Any] | None,
    *,
    path: str,
    action: str,
) -> bool:
    policy = resolve_relation_policy(relation_policies, path)
    action_name = str(action or "").lower()
    if not action_name:
        return True

    blocked_actions = {str(item).lower() for item in policy.get("blocked", [])}
    allowed_actions = {str(item).lower() for item in policy.get("allowed", [])}
    default_allow = bool(policy.get("default_allow", True))

    if action_name in blocked_actions:
        return False
    if allowed_actions:
        return action_name in allowed_actions
    if action_name not in DEFAULT_ACTIONS:
        return default_allow
    return default_allow


def enforce_action_allowed(
    relation_policies: dict[str, Any] | None,
    *,
    path: str,
    action: str,
) -> None:
    if is_action_allowed(relation_policies, path=path, action=action):
        return
    raise GraphQLError(
        f"Nested action '{action}' is not allowed for relation '{normalize_path(path)}'."
    )
