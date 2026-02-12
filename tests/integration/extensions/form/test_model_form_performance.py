from time import perf_counter

import pytest

from rail_django.extensions.form.extractors.model_form_contract_extractor import (
    ModelFormContractExtractor,
)
from rail_django.extensions.form.schema.mutations import execute_atomic_bulk
from test_app.models import Category, Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def generated_contract_enabled():
    previous = getattr(Product.GraphQLMeta, "custom_metadata", None)
    Product.GraphQLMeta.custom_metadata = {"generated_form": {"enabled": True}}
    if hasattr(Product, "_graphql_meta_instance"):
        delattr(Product, "_graphql_meta_instance")
    yield
    if previous is None and hasattr(Product.GraphQLMeta, "custom_metadata"):
        delattr(Product.GraphQLMeta, "custom_metadata")
    else:
        Product.GraphQLMeta.custom_metadata = previous
    if hasattr(Product, "_graphql_meta_instance"):
        delattr(Product, "_graphql_meta_instance")


def test_contract_generation_latency_budget(generated_contract_enabled):
    extractor = ModelFormContractExtractor(schema_name="default")
    started = perf_counter()
    contract = extractor.extract_contract(
        "test_app",
        "Product",
        mode="CREATE",
        enforce_opt_in=True,
    )
    elapsed = perf_counter() - started
    assert contract["model_name"] == "Product"
    assert elapsed <= 0.8


def test_bulk_atomic_mutation_timing_budget():
    category = Category.objects.create(name="Perf", description="")

    def mutator(item, _row_index):
        return Product.objects.create(
            name=item["name"],
            price=item["price"],
            category=category,
        )

    items = [{"name": f"Product {idx}", "price": idx + 1} for idx in range(200)]
    started = perf_counter()
    result = execute_atomic_bulk(items=items, mutator=mutator)
    elapsed = perf_counter() - started

    assert result["ok"] is True
    assert len(result["objects"]) == 200
    assert elapsed <= 5
