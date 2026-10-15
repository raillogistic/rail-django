"""Custom GraphQL field arguments must reach model methods, including pagination."""

from types import SimpleNamespace
import graphene
import pytest
from rail_django.core.decorators import field
from rail_django.generators.types import TypeGenerator
from rail_django.generators.introspector import ModelIntrospector
from test_app.models import Category

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("accepts_info", [True, False])
def test_custom_field_arguments_are_forwarded(monkeypatch, accepts_info):
    """Declared Graphene arguments are forwarded for both supported method signatures."""
    if accepts_info:
        @field(type=graphene.Field(graphene.Int, page=graphene.Int(default_value=1)))
        def paged_count(self, info, page=1):
            return page
    else:
        @field(type=graphene.Field(graphene.Int, page=graphene.Int(default_value=1)))
        def paged_count(self, *, page=1):
            return page
    monkeypatch.setattr(Category, "paged_count", paged_count, raising=False)
    ModelIntrospector.clear_cache()
    generator = TypeGenerator()
    generated = generator.generate_object_type(Category)
    instance = Category(name="Arguments")
    assert generated.resolve_paged_count(instance, SimpleNamespace(), page=2) == 2
    assert generated.resolve_paged_count(instance, SimpleNamespace()) == 1
