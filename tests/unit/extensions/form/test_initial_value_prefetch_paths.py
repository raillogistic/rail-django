"""Regression coverage for reverse relations with default Django accessors."""

from django.contrib.auth import get_user_model
import pytest

from rail_django.extensions.form.extractors.base import FormConfigExtractor

pytestmark = pytest.mark.unit


def test_prefetch_paths_use_reverse_accessor_names():
    """A reverse query name such as logentry cannot be passed to prefetch_related."""
    model = get_user_model()
    reverse = next(field for field in model._meta.get_fields() if field.one_to_many)
    _, prefetch = FormConfigExtractor()._collect_relation_paths(model)

    assert reverse.get_accessor_name() in prefetch
    if reverse.name != reverse.get_accessor_name():
        assert reverse.name not in prefetch
