import pytest

from rail_django.extensions.form.extractors.model_form_contract_extractor import (
    ModelFormContractExtractor,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def contract_payload_fixture():
    return {
        "id": "test_app.Product.CREATE",
        "app_label": "test_app",
        "model_name": "Product",
        "mode": "CREATE",
        "version": "1",
        "config_version": "abc123",
        "fields": [
            {"path": "name", "kind": "TEXT"},
            {"path": "price", "kind": "DECIMAL"},
        ],
        "sections": [{"id": "main", "field_paths": ["name", "price"]}],
        "mutation_bindings": {
            "create_operation": "createProduct",
            "update_operation": "updateProduct",
            "bulk_create_operation": "bulkCreateProduct",
            "bulk_update_operation": "bulkUpdateProduct",
            "update_target_policy": "PRIMARY_KEY_ONLY",
            "bulk_commit_policy": "ATOMIC",
            "conflict_policy": "REJECT_STALE",
        },
        "error_policy": {
            "canonical_form_error_key": "__all__",
            "field_path_notation": "dot",
            "bulk_row_prefix_pattern": "items.<row>.<field>",
        },
    }


def test_generated_contract_fixture_shape(contract_payload_fixture):
    payload = contract_payload_fixture
    assert payload["model_name"] == "Product"
    assert payload["mutation_bindings"]["create_operation"] == "createProduct"
    assert payload["error_policy"]["canonical_form_error_key"] == "__all__"


def test_model_form_contract_extractor_builds_mutation_bindings():
    extractor = ModelFormContractExtractor(schema_name="default")
    contract = extractor.extract_contract(
        "test_app",
        "Product",
        mode="CREATE",
        enforce_opt_in=False,
    )
    bindings = contract["mutation_bindings"]
    assert bindings["create_operation"] == "createProduct"
    assert bindings["update_target_policy"] == "PRIMARY_KEY_ONLY"


def test_default_sections_include_forward_relations_in_declared_order():
    extractor = ModelFormContractExtractor(schema_name="default")
    contract = extractor.extract_contract(
        "test_app",
        "Post",
        mode="CREATE",
        enforce_opt_in=False,
    )

    default_section = contract["sections"][0]
    field_paths = default_section["field_paths"]

    assert field_paths.index("title") < field_paths.index("category")
    assert field_paths.index("category") < field_paths.index("tags")
