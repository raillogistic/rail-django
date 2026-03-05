from types import SimpleNamespace

import pytest

from rail_django.extensions.form.schema.queries import FormQuery

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _info_stub():
    return SimpleNamespace(
        context=SimpleNamespace(
            user=None,
            schema_name="default",
        )
    )


def test_model_form_contract_hides_hidden_fields_by_default(monkeypatch):
    payload = {
        "id": "test_app.Product.CREATE",
        "app_label": "test_app",
        "model_name": "Product",
        "mode": "CREATE",
        "version": "1",
        "config_version": "1",
        "generated_at": None,
        "fields": [
            {"field_name": "id", "hidden": True},
            {"field_name": "name", "hidden": False},
        ],
    }

    monkeypatch.setattr(
        "rail_django.extensions.form.schema.queries.ModelFormContractExtractor.extract_contract",
        lambda *_args, **_kwargs: dict(payload),
    )

    result = FormQuery().resolve_model_form_contract(
        _info_stub(),
        app_label="test_app",
        model_name="Product",
    )

    assert [field["field_name"] for field in result["fields"]] == ["name"]


def test_model_form_contract_shows_hidden_fields_when_read_only_true(monkeypatch):
    payload = {
        "id": "test_app.Product.CREATE",
        "app_label": "test_app",
        "model_name": "Product",
        "mode": "CREATE",
        "version": "1",
        "config_version": "1",
        "generated_at": None,
        "fields": [
            {"field_name": "id", "hidden": True},
            {"field_name": "name", "hidden": False},
        ],
    }

    monkeypatch.setattr(
        "rail_django.extensions.form.schema.queries.ModelFormContractExtractor.extract_contract",
        lambda *_args, **_kwargs: dict(payload),
    )

    result = FormQuery().resolve_model_form_contract(
        _info_stub(),
        app_label="test_app",
        model_name="Product",
        read_only=True,
    )

    assert [field["field_name"] for field in result["fields"]] == ["id", "name"]
