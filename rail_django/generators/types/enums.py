"""
Enum helpers for choice fields.
"""

from typing import Any, Dict, Optional, Type
import re

import graphene
from django.db.models.fields import Field
from django.db import models


def build_enum_name(self, model: type[models.Model], field_name: str) -> str:
    """
    Purpose: Build a stable GraphQL Enum name for a model field.
    """
    return f"{model.__name__}_{field_name}_Enum"


def get_or_create_enum_for_field(
    self, model: type[models.Model], django_field: Field
) -> Optional[type[graphene.Enum]]:
    """
    Purpose: Create or retrieve a GraphQL Enum type for a Django field with choices.
    """
    # Validate choices presence
    choices = getattr(django_field, "choices", None)
    if not choices:
        return None

    # Build a cache key unique per schema/model/field
    enum_name = self._build_enum_name(model, django_field.name)
    cache_key = f"{self.schema_name}:{enum_name}"
    if cache_key in self._enum_registry:
        return self._enum_registry[cache_key]

    # Prepare enum members from choices
    # Choices may be provided as list of (value, label) tuples
    # We derive enum member names from values for stability
    def _normalize_member_name(raw_value: Any, index: int) -> str:
        text = str(raw_value).strip()
        # Uppercase, replace non-alphanumeric with underscores
        candidate = re.sub(r"[^a-zA-Z0-9]+", "_", text).upper()
        if not candidate or not candidate[0].isalpha():
            candidate = f"CHOICE_{candidate}" if candidate else "CHOICE"
        # Ensure uniqueness by appending index if duplicates
        return f"{candidate}_{index}" if candidate in member_names else candidate

    member_names: set = set()
    enum_members: dict[str, Any] = {}
    for idx, choice in enumerate(choices):
        try:
            value, label = choice
        except Exception:
            # Fallback if choice is a single value
            value, label = choice, str(choice)
        name = _normalize_member_name(value, idx)
        member_names.add(name)
        enum_members[name] = value

    # Create the Graphene Enum
    try:
        enum_type = graphene.Enum(enum_name, enum_members)
    except Exception:
        # As a safety fallback, if Graphene fails due to naming, prefix with schema
        safe_enum_name = f"{self.schema_name}_{enum_name}"
        enum_type = graphene.Enum(safe_enum_name, enum_members)

    # Cache and return
    self._enum_registry[cache_key] = enum_type
    return enum_type
