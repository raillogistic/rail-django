"""Unit tests for grouping query generation."""

from types import SimpleNamespace

import pytest
from django.contrib.sessions.models import Session
from django.utils import timezone

from rail_django.core.settings import QueryGeneratorSettings
from rail_django.generators.queries import QueryGenerator
from rail_django.generators.types import TypeGenerator

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_grouping_query_handles_non_id_primary_key_model():
    """Grouping resolver should work for models whose PK is not named 'id'."""
    Session.objects.create(
        session_key="grouping-test-session",
        session_data="{}",
        expire_date=timezone.now(),
    )

    generator = QueryGenerator(
        TypeGenerator(),
        settings=QueryGeneratorSettings(require_model_permissions=False),
    )
    grouping_field = generator.generate_grouping_query(Session)

    info = SimpleNamespace(context=SimpleNamespace(user=None))
    resolver = getattr(grouping_field.resolver, "__wrapped__", grouping_field.resolver)
    result = resolver(None, info, group_by="expire_date")

    assert isinstance(result, list)
