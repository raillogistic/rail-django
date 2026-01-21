"""
Relationship discovery logic for ModelIntrospector.
"""

from typing import Dict
from django.db import models

class RelationshipDiscoveryMixin:
    """Mixin for discovering model relationships."""

    def get_manytoone_relations(self) -> dict[str, type[models.Model]]:
        """Get reverse many-to-one relationships."""
        reverse_relations = {}
        if not self._meta: return reverse_relations
        if hasattr(self._meta, "related_objects"):
            for rel in self._meta.related_objects:
                if type(rel) == models.ManyToOneRel:
                    reverse_relations[rel.get_accessor_name()] = rel.related_model
        return reverse_relations

    def get_reverse_relations(self) -> dict[str, type[models.Model]]:
        """Get all reverse relationships."""
        reverse_relations = {}
        if not self._meta: return reverse_relations
        if hasattr(self._meta, "related_objects"):
            for rel in self._meta.related_objects:
                reverse_relations[rel.get_accessor_name()] = rel.related_model
        return reverse_relations
