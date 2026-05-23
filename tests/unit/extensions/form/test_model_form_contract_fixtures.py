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
    assert isinstance(contract["order"], list)


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
                    "read_only": True,
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
    assert relations[0]["read_only"] is True


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
    order = contract["order"]

    assert field_paths.index("title") < field_paths.index("category")
    assert field_paths.index("category") < field_paths.index("tags")
    assert order.index("title") < order.index("category")
    assert order.index("category") < order.index("tags")


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


def test_model_form_contract_field_read_only_not_forced_by_permission_writable():
    extractor = ModelFormContractExtractor(schema_name="default")
    fields = extractor._build_fields(
        {
            "fields": [
                {
                    "name": "title",
                    "field_name": "title",
                    "label": "Title",
                    "input_type": "TEXT",
                    "graphql_type": "String",
                    "python_type": "str",
                    "required": True,
                    "nullable": False,
                    "read_only": False,
                    "hidden": False,
                    "validators": [],
                }
            ]
        },
        mode="CREATE",
        contract_permissions={
            "field_permissions": [
                {
                    "field": "title",
                    "can_read": True,
                    "can_write": False,
                    "visibility": "VISIBLE",
                }
            ]
        },
    )

    assert fields[0]["writable"] is False
    assert fields[0]["read_only"] is False


def test_model_form_contract_field_read_only_when_non_editable():
    extractor = ModelFormContractExtractor(schema_name="default")
    fields = extractor._build_fields(
        {
            "fields": [
                {
                    "name": "externalId",
                    "field_name": "external_id",
                    "label": "External ID",
                    "input_type": "TEXT",
                    "graphql_type": "String",
                    "python_type": "str",
                    "required": False,
                    "nullable": False,
                    "editable": False,
                    "read_only": False,
                    "hidden": False,
                    "validators": [],
                }
            ]
        },
        mode="CREATE",
        contract_permissions={"field_permissions": []},
    )

    assert fields[0]["read_only"] is True


def test_model_form_contract_extractor_includes_help_text():
    """
    Vérifie que l'extracteur inclut correctement le texte d'aide (help_text) du champ.
    """
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
                    "help_text": "Choisissez le statut de la commande.",
                    "validators": [],
                }
            ]
        },
        mode="CREATE",
        contract_permissions={"field_permissions": []},
    )

    assert fields[0]["help_text"] == "Choisissez le statut de la commande."


def test_field_extractor_extracts_constraints_from_validators():
    """
    Vérifie que l'extracteur de champs extrait correctement les contraintes
    (min_value, max_value, min_length, max_length, pattern, allowed_extensions)
    à partir des validateurs Django (MinValueValidator, MaxValueValidator, etc.).
    """
    from django.core.validators import (
        MinValueValidator,
        MaxValueValidator,
        MinLengthValidator,
        MaxLengthValidator,
        RegexValidator,
        FileExtensionValidator,
    )
    from django.db import models
    from rail_django.extensions.form.extractors.field_extractor import FieldExtractorMixin

    class DummyModel(models.Model):
        class Meta:
            app_label = "test_app"

    # Mock un champ Django avec différents validateurs
    field = models.IntegerField(
        validators=[
            MinValueValidator(10),
            MaxValueValidator(50),
        ]
    )
    field.name = "age"
    field.model = DummyModel

    extractor = FieldExtractorMixin()
    res = extractor._extract_field(
        model=DummyModel,
        field=field,
        user=None,
        mode="CREATE",
    )

    assert res is not None
    assert res["constraints"]["min_value"] == 10.0
    assert res["constraints"]["max_value"] == 50.0

    # Mock un champ de caractères avec Min/Max Length et Regex
    char_field = models.CharField(
        max_length=100,
        validators=[
            MinLengthValidator(5),
            RegexValidator(r"^[A-Z]+$"),
        ]
    )
    char_field.name = "code"
    char_field.model = DummyModel

    res_char = extractor._extract_field(
        model=DummyModel,
        field=char_field,
        user=None,
        mode="CREATE",
    )
    assert res_char is not None
    assert res_char["constraints"]["min_length"] == 5
    assert res_char["constraints"]["max_length"] == 100
    assert res_char["constraints"]["pattern"] == r"^[A-Z]+$"

    # Mock un FileField avec FileExtensionValidator
    file_field = models.FileField(
        validators=[
            FileExtensionValidator(allowed_extensions=["pdf", "docx"]),
        ]
    )
    file_field.name = "document"
    file_field.model = DummyModel

    res_file = extractor._extract_field(
        model=DummyModel,
        field=file_field,
        user=None,
        mode="CREATE",
    )
    assert res_file is not None
    assert res_file["constraints"]["allowed_extensions"] == ["pdf", "docx"]


