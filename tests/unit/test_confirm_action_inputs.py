"""Confirm actions retain required revision/replay arguments from their method signatures."""

import pytest
from rail_django.core.decorators import confirm_action, mutation
from rail_django.generators.introspector import ModelIntrospector
from rail_django.generators.types import TypeGenerator
from rail_django.generators.mutations import MutationGenerator
from test_app.models import Category

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("with_arguments", [True, False])
def test_confirm_action_inputs_follow_method_signature(monkeypatch, with_arguments):
    """Argument-free confirmations remain unchanged; required business inputs are generated."""
    if with_arguments:
        @confirm_action(title="Accept", message="Accept this revision?")
        @mutation()
        def accept(self, revision: int, key: str) -> bool:
            return True
    else:
        @confirm_action(title="Accept", message="Accept?")
        @mutation()
        def accept(self) -> bool:
            return True
    monkeypatch.setattr(Category, "accept", accept, raising=False)
    ModelIntrospector.clear_cache()
    method = ModelIntrospector.for_model(Category).get_model_methods()["accept"]
    generated = MutationGenerator(TypeGenerator()).generate_method_mutation(Category, method)
    assert ("input" in generated._meta.arguments) is with_arguments
    if with_arguments:
        fields = generated._meta.arguments["input"]._meta.fields
        assert set(fields) == {"revision", "key"}
        from types import SimpleNamespace
        from rail_django.core.middleware.auth import FieldPermissionMiddleware
        middleware = FieldPermissionMiddleware()
        monkeypatch.setattr(middleware, "_resolve_mutation_model_class", lambda info: Category)
        info = SimpleNamespace(return_type=SimpleNamespace(graphene_type=generated))
        payload = {"id": "1", "input": {"revision": 2, "key": "retry"}}
        assert middleware._enforce_input_permissions(None, info, payload) == payload
        from graphql import GraphQLError
        with pytest.raises(GraphQLError, match="Undeclared action inputs"):
            middleware._enforce_input_permissions(None, info, {"input": {"password": "forged"}})
