"""
Input normalization for Form API mutations.
"""

from __future__ import annotations

from typing import Any, Dict

from graphql import GraphQLError

from .relation_policy import enforce_action_allowed
from .relation_normalizer import normalize_relation_input
from .type_coercion import coerce_value

PRIMARY_KEY_FIELDS = {"id", "pk", "object_id", "objectId"}


def normalize_values(values: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    relations: Dict[str, Dict[str, Any]] = {}
    for relation in config.get("relations", []) or []:
        if not isinstance(relation, dict):
            continue
        for alias in (
            relation.get("name"),
            relation.get("field_name"),
            relation.get("path"),
        ):
            key = str(alias or "").strip()
            if key:
                relations[key] = relation
    relation_policies = config.get("relation_policies") or {}

    for key, value in (values or {}).items():
        relation = relations.get(key)
        if relation:
            relation_input = normalize_relation_input(value)
            for action_name in relation_input.keys():
                enforce_action_allowed(
                    relation_policies,
                    path=relation.get("field_name")
                    or relation.get("path")
                    or key,
                    action=action_name,
                )
            normalized[key] = relation_input
        else:
            normalized[key] = coerce_value(value)
    return normalized


def enforce_primary_key_only_update_target(target: Dict[str, Any]) -> str:
    if not isinstance(target, dict):
        raise GraphQLError("Update target must be an object containing a primary key.")

    accepted = [name for name in PRIMARY_KEY_FIELDS if name in target]
    if len(accepted) != 1:
        raise GraphQLError(
            "Update target must provide exactly one primary-key field (id/pk/objectId/object_id)."
        )

    pk_field = accepted[0]
    pk_value = target.get(pk_field)
    if pk_value in (None, ""):
        raise GraphQLError("Update target primary key value is required.")

    illegal = [key for key in target.keys() if key not in PRIMARY_KEY_FIELDS]
    if illegal:
        raise GraphQLError(
            "Update target must only contain primary-key fields; unsupported keys: "
            + ", ".join(sorted(illegal))
        )

    return str(pk_value)
