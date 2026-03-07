import os
import django
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rail_django.config.framework_settings")
django.setup()

from rail_django.extensions.form.extractors.base import FormConfigExtractor
from tests.models import TestProject


@pytest.mark.django_db
def test_form_config_extractor_basic():
    extractor = FormConfigExtractor()
    config = extractor.extract("rail_django", "SchemaRegistryModel")

    assert config["app"] == "rail_django"
    assert config["model"] == "SchemaRegistryModel"
    assert "fields" in config
    assert "relations" in config
    assert "permissions" in config
    assert config["config_version"]


@pytest.mark.django_db
def test_form_config_version_stable():
    extractor = FormConfigExtractor()
    config1 = extractor.extract("rail_django", "SchemaRegistryModel")
    config2 = extractor.extract("rail_django", "SchemaRegistryModel")
    assert config1["config_version"] == config2["config_version"]


@pytest.mark.django_db
def test_form_data_includes_initial_values():
    extractor = FormConfigExtractor()
    config = extractor.extract("rail_django", "SchemaRegistryModel")

    from rail_django.models import SchemaRegistryModel

    instance = SchemaRegistryModel.objects.create(
        name="test-schema",
        description="Test",
        version="1.0.0",
    )

    values = extractor.extract_initial_values(
        "rail_django", "SchemaRegistryModel", object_id=str(instance.pk)
    )
    assert values
    assert "name" in values


def test_collect_relation_paths_prefetches_descendants_of_reverse_relations():
    extractor = FormConfigExtractor()

    select_related_paths, prefetch_related_paths = extractor._collect_relation_paths(
        TestProject,
        include_nested=False,
        nested_field_set={"assignments"},
        max_nested_depth=2,
    )

    assert "assignments" in prefetch_related_paths
    assert "assignments__projet" in prefetch_related_paths
    assert "assignments__employe" in prefetch_related_paths
    assert "assignments__projet" not in select_related_paths
    assert "assignments__employe" not in select_related_paths
