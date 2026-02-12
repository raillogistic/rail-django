import pytest

from rail_django.extensions.form.normalization.error_normalizer import normalize_bulk_errors
from rail_django.extensions.form.schema.mutations import execute_atomic_bulk
from test_app.models import Category, Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_bulk_create_update_atomic_rollback_behavior():
    category = Category.objects.create(name="Bulk", description="")
    before = Product.objects.count()

    def mutator(item, row_index):
        if row_index == 1:
            raise ValueError("row failed")
        return Product.objects.create(
            name=item["name"],
            price=item["price"],
            category=category,
        )

    result = execute_atomic_bulk(
        items=[
            {"name": "First", "price": 10},
            {"name": "Second", "price": 20},
        ],
        mutator=mutator,
    )

    assert result["ok"] is False
    assert result["objects"] == []
    assert Product.objects.count() == before


def test_bulk_error_paths_include_row_index_and_form_fallback():
    normalized = normalize_bulk_errors(
        [
            {"row_index": 2, "field": "name", "message": "Invalid name"},
            {"row_index": 3, "field": None, "message": "Row failed"},
        ]
    )
    assert normalized[0]["field"] == "items.2.name"
    assert normalized[1]["field"] == "items.3.__all__"
