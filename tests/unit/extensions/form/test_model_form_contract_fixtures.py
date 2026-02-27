import pytest
from types import SimpleNamespace

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


def test_model_form_contract_extractor_includes_field_choices_in_constraints():
    extractor = ModelFormContractExtractor(schema_name="default")
    fields = extractor._build_fields(
        {
            "fields": [
                {
                    "name": "status",
                    "field_name": "status",
                    "label": "Status",
                    "input_type": "SELECT",
                    "graphql_type": "String",
                    "python_type": "str",
                    "required": False,
                    "nullable": False,
                    "read_only": False,
                    "hidden": False,
                    "default_value": None,
                    "constraints": {"max_length": 16},
                    "choices": [
                        {"value": "placed", "label": "Placed"},
                        {"value": "paid", "label": "Paid"},
                    ],
                    "validators": [],
                    "input_props": {},
                    "metadata": None,
                }
            ]
        },
        mode="CREATE",
        contract_permissions={"field_permissions": []},
    )

    assert fields[0]["kind"] == "CHOICE"
    assert fields[0]["constraints"]["max_length"] == 16
    assert fields[0]["constraints"]["choices"] == [
        {"value": "placed", "label": "Placed"},
        {"value": "paid", "label": "Paid"},
    ]


def test_model_form_contract_extractor_relations_include_required_and_nullable():
    extractor = ModelFormContractExtractor(schema_name="default")
    relations = extractor._build_relations(
        {
            "relations": [
                {
                    "name": "category",
                    "field_name": "category",
                    "label": "Category",
                    "relation_type": "FOREIGN_KEY",
                    "is_to_many": False,
                    "required": True,
                    "nullable": False,
                    "related_app": "test_app",
                    "related_model": "Category",
                    "operations": {"can_connect": True, "can_set": True},
                }
            ]
        },
        include_nested=False,
        mode="CREATE",
        contract_permissions={"field_permissions": []},
    )

    assert relations[0]["name"] == "category"
    assert relations[0]["required"] is True
    assert relations[0]["nullable"] is False


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


def test_extract_contract_page_extracts_only_paginated_refs(monkeypatch):
    extractor = ModelFormContractExtractor(schema_name="default")

    models = {
        ("app_one", "Alpha"): SimpleNamespace(
            __name__="Alpha",
            _meta=SimpleNamespace(app_label="app_one"),
        ),
        ("app_two", "Beta"): SimpleNamespace(
            __name__="Beta",
            _meta=SimpleNamespace(app_label="app_two"),
        ),
        ("app_three", "Gamma"): SimpleNamespace(
            __name__="Gamma",
            _meta=SimpleNamespace(app_label="app_three"),
        ),
    }

    monkeypatch.setattr(
        extractor,
        "_resolve_model",
        lambda app_label, model_name: models[(app_label, model_name)],
    )
    monkeypatch.setattr(
        "rail_django.extensions.form.extractors.model_form_contract_extractor.is_generated_form_enabled",
        lambda _model: True,
    )

    extracted_refs: list[tuple[str, str]] = []

    def _fake_extract_contract(app_label, model_name, **_kwargs):
        extracted_refs.append((app_label, model_name))
        return {
            "id": f"{app_label}.{model_name}.CREATE",
            "app_label": app_label,
            "model_name": model_name,
        }

    monkeypatch.setattr(extractor, "extract_contract", _fake_extract_contract)

    result = extractor.extract_contract_page(
        [
            {"app_label": "app_one", "model_name": "Alpha"},
            {"app_label": "app_two", "model_name": "Beta"},
            {"app_label": "app_three", "model_name": "Gamma"},
        ],
        page=2,
        per_page=1,
    )

    assert result["total"] == 3
    assert len(result["results"]) == 1
    assert extracted_refs == [("app_two", "Beta")]
