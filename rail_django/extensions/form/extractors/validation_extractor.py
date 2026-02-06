"""
Validation extraction for Form API.
"""

from __future__ import annotations

from typing import Any, Optional

from django.db import models


class ValidationExtractorMixin:
    """Mixin for extracting cross-field validation rules."""

    def _extract_validation_rules(
        self,
        model: type[models.Model],
        *,
        graphql_meta: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        if graphql_meta is None:
            return []
        rules = getattr(graphql_meta, "validation_rules", None)
        if isinstance(rules, list):
            return rules
        return []
