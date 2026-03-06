from types import SimpleNamespace

import pytest

from rail_django.extensions.form.schema.queries import FormQuery

pytestmark = [pytest.mark.unit]


def test_resolve_form_data_reuses_loaded_instance(monkeypatch):
    shared_instance = object()
    calls: list[object] = []

    class FakeExtractor:
        def __init__(self, *args, **kwargs):
            pass

        def _load_instance(self, model_cls, object_id):
            assert object_id == "123"
            return shared_instance

        def extract(self, *args, **kwargs):
            calls.append(kwargs.get("instance"))
            return {"config": True}

        def extract_initial_values(self, *args, **kwargs):
            calls.append(kwargs.get("instance"))
            return {"name": "Widget"}

    monkeypatch.setattr(
        "rail_django.extensions.form.schema.queries.FormConfigExtractor",
        FakeExtractor,
    )
    monkeypatch.setattr(
        "rail_django.extensions.form.schema.queries.apps.get_model",
        lambda app, model: object(),
    )

    info = SimpleNamespace(context=SimpleNamespace(user=None, schema_name="default"))
    result = FormQuery().resolve_form_data(
        info,
        app="test_app",
        model="Product",
        object_id="123",
        mode="UPDATE",
    )

    assert result["config"] == {"config": True}
    assert result["initial_values"] == {"name": "Widget"}
    assert calls == [shared_instance, shared_instance]
