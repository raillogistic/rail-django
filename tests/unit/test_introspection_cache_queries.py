"""Different introspection selections and variables must never share a cached response."""

from types import SimpleNamespace
import graphene
import pytest
from django.core.cache import cache
from django.test import RequestFactory
from rail_django.graphql.views.multi_schema import MultiSchemaGraphQLView

pytestmark = pytest.mark.unit


class Query(graphene.ObjectType):
    """Small schema sufficient to exercise the real GraphQL view execution/cache path."""

    sample = graphene.String()


def test_selections_variables_and_operations_keep_their_own_response(monkeypatch):
    """Replay __type for String/Query, an aliased selection and a named operation."""
    view = MultiSchemaGraphQLView(schema=graphene.Schema(query=Query))
    monkeypatch.setattr(view, "_should_cache_introspection", lambda request, query: True)
    monkeypatch.setattr(view, "_get_schema_name", lambda request: "cache-regression")
    monkeypatch.setattr(view, "_resolve_request_user", lambda request: SimpleNamespace(pk=123))
    request = RequestFactory().post("/graphql/")
    cache.clear()
    query = 'query($name:String!) { __type(name:$name) {name fields {name}} }'
    for name, fields in [("Query", [{"name": "sample"}]), ("String", None), ("Query", [{"name": "sample"}])]:
        result = view.execute_graphql_request(request, {}, query, {"name": name}, None)
        assert result.errors is None
        assert result.data == {"__type": {"name": name, "fields": fields}}
    aliased = view.execute_graphql_request(request, {}, 'query { scalar:__type(name:"String") {name} }', {}, None)
    assert aliased.data == {"scalar": {"name": "String"}}
    multiple = 'query A { __type(name:"String") {name} } query B { __type(name:"Query") {name} }'
    first = view.execute_graphql_request(request, {}, multiple, {}, "A")
    second = view.execute_graphql_request(request, {}, multiple, {}, "B")
    assert first.data == {"__type": {"name": "String"}}
    assert second.data == {"__type": {"name": "Query"}}
    cache.clear()
