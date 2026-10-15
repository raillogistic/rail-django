"""Graphene must not recreate reverse fields explicitly excluded by GraphQLMeta."""

import pytest
from rail_django.core.meta import GraphQLMeta
from rail_django.generators.types import TypeGenerator
from test_app.models import Category

pytestmark = pytest.mark.unit


def test_reverse_exclusion_reaches_generated_object_and_input_types(monkeypatch):
    """Exclude the real Category.posts reverse FK while leaving ordinary identity fields."""
    class RestrictedMeta(GraphQLMeta):
        """Fixture declaration matching application-level reverse exclusions."""

        fields = GraphQLMeta.Fields(exclude=["posts"])

    monkeypatch.setattr(Category, "GraphQLMeta", RestrictedMeta, raising=False)
    monkeypatch.setattr(Category, "_graphql_meta_instance", GraphQLMeta(Category), raising=False)
    generator = TypeGenerator()
    generated = generator.generate_object_type(Category)
    assert "name" in generated._meta.fields
    assert "posts" not in generated._meta.fields
    assert "posts_count" not in generated._meta.fields
    assert "posts_stats" not in generated._meta.fields
    inputs = generator.generate_input_type(Category, mutation_type="update")
    assert "posts" not in inputs._meta.fields
