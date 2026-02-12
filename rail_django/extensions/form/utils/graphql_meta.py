"""
Helpers for accessing GraphQLMeta configuration on Django models.
"""

from __future__ import annotations

from typing import Any

from ....utils.graphql_meta import get_model_graphql_meta


def get_graphql_meta(model: Any) -> Any:
    return get_model_graphql_meta(model)


def get_model_form_mutation_bindings(model: Any) -> dict[str, Any]:
    model_name = model.__name__
    return {
        "create_operation": f"create{model_name}",
        "update_operation": f"update{model_name}",
        "bulk_create_operation": f"bulkCreate{model_name}",
        "bulk_update_operation": f"bulkUpdate{model_name}",
        "update_target_policy": "PRIMARY_KEY_ONLY",
        "bulk_commit_policy": "ATOMIC",
        "conflict_policy": "REJECT_STALE",
    }
