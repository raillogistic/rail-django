import pytest
from django.apps import apps

from rail_django.extensions.metadata.detail_extractor import DetailContractExtractor

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_relation_guard_respects_depth_limit():
    extractor = DetailContractExtractor(schema_name="test_detail_depth")
    state = extractor._walk_relation_graph_guard(
        root_label="test_app.Product",
        related_app="test_app",
        related_model="Category",
        max_depth=1,
    )

    assert state["blocked"] is False
    assert state["depth"] == 1
    assert state["path"] == ["test_app.Product", "test_app.Category"]


def test_relation_guard_detects_cycles_without_unbounded_walk():
    extractor = DetailContractExtractor(schema_name="test_detail_depth")
    state = extractor._walk_relation_graph_guard(
        root_label="test_app.Product",
        related_app="test_app",
        related_model="Category",
        max_depth=4,
    )

    assert state["blocked"] is False
    assert state["cycle_detected"] is True
    assert state["depth"] <= 4


def test_relation_source_metadata_includes_depth_and_cycle_flags():
    extractor = DetailContractExtractor(schema_name="test_detail_depth")
    model_cls = apps.get_model("test_app", "Product")
    model_schema = {
        "relationships": [
            {
                "name": "category",
                "related_app": "test_app",
                "related_model": "Category",
                "readable": True,
                "is_reverse": False,
                "is_to_many": False,
            }
        ],
        "custom_metadata": {
            "detail": {
                "max_depth": 2,
            }
        },
    }

    sources = extractor._extract_relation_data_sources(model_cls, model_schema)
    assert len(sources) == 1
    source = sources[0]
    pagination = source["pagination"]
    assert pagination["max_depth"] == 2
    assert pagination["cycle_guard_enabled"] is True
    assert "cycle_detected" in pagination
