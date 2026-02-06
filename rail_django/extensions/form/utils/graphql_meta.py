"""
Helpers for accessing GraphQLMeta configuration on Django models.
"""

from __future__ import annotations

from typing import Any

from ....utils.graphql_meta import get_model_graphql_meta


def get_graphql_meta(model: Any) -> Any:
    return get_model_graphql_meta(model)
