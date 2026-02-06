"""
Automation extraction for Form API (conditional/computed rules).
"""

from __future__ import annotations

from typing import Any, Optional

from django.db import models


class AutomationExtractorMixin:
    """Mixin for extracting automation rules."""

    def _extract_conditional_rules(
        self,
        model: type[models.Model],
        *,
        graphql_meta: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        if graphql_meta is None:
            return []
        rules = getattr(graphql_meta, "conditional_rules", None)
        if isinstance(rules, list):
            return [
                {
                    "id": rule.get("id") or rule.get("name") or "",
                    "target_field": rule.get("targetField") or rule.get("target_field"),
                    "action": rule.get("action"),
                    "dsl_version": rule.get("dslVersion", "1"),
                    "expression": rule.get("expression"),
                    "logic": rule.get("logic", "AND"),
                    "conditions": rule.get("conditions", []),
                }
                for rule in rules
            ]
        return []

    def _extract_computed_fields(
        self,
        model: type[models.Model],
        *,
        graphql_meta: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        if graphql_meta is None:
            return []
        fields = getattr(graphql_meta, "computed_fields", None)
        if isinstance(fields, list):
            return [
                {
                    "name": field.get("name"),
                    "expression": field.get("expression", ""),
                    "dsl_version": field.get("dslVersion", "1"),
                    "dependencies": field.get("dependencies", []),
                    "trigger": field.get("trigger", "ON_CHANGE"),
                    "client_side": field.get("clientSide", True),
                }
                for field in fields
            ]
        return []
