from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rail_django.core.middleware.performance import QueryComplexityMiddleware
from rail_django.core.middleware.security import GraphQLAuditMiddleware
from rail_django.testing import build_request, override_rail_settings


pytestmark = pytest.mark.unit


def _make_info(
    *,
    operation_type: str,
    field_name: str,
    operation_name: str | None = None,
):
    operation = SimpleNamespace(operation=SimpleNamespace(value=operation_type))
    if operation_name:
        operation.name = SimpleNamespace(value=operation_name)
    else:
        operation.name = None

    return SimpleNamespace(
        operation=operation,
        field_name=field_name,
        path=SimpleNamespace(prev=None),
        context=build_request(),
        variable_values={},
    )


def test_graphql_audit_skips_queries_by_default(monkeypatch):
    emitted = Mock()
    monkeypatch.setattr("rail_django.security.security.emit", emitted)

    middleware = GraphQLAuditMiddleware(schema_name="test")
    info = _make_info(operation_type="query", field_name="customers")

    result = middleware.resolve(lambda root, gql_info, **kwargs: "ok", None, info)

    assert result == "ok"
    emitted.assert_not_called()


def test_graphql_audit_records_listed_queries(monkeypatch):
    emitted = Mock()
    monkeypatch.setattr("rail_django.security.security.emit", emitted)

    with override_rail_settings(
        global_settings={
            "security_settings": {"audited_query_fields": ["customers"]}
        }
    ):
        middleware = GraphQLAuditMiddleware(schema_name="test")
        info = _make_info(operation_type="query", field_name="customers")

        result = middleware.resolve(lambda root, gql_info, **kwargs: "ok", None, info)

    assert result == "ok"
    emitted.assert_called_once()
    assert emitted.call_args.args[0].value == "data.read"


def test_graphql_audit_records_mutations_by_default(monkeypatch):
    emitted = Mock()
    monkeypatch.setattr("rail_django.security.security.emit", emitted)

    middleware = GraphQLAuditMiddleware(schema_name="test")
    info = _make_info(operation_type="mutation", field_name="createCustomer")

    result = middleware.resolve(lambda root, gql_info, **kwargs: "ok", None, info)

    assert result == "ok"
    emitted.assert_called_once()
    assert emitted.call_args.args[0].value == "data.create"


def test_query_limits_skip_unlisted_queries_by_default():
    middleware = QueryComplexityMiddleware(schema_name="test")
    middleware.complexity_analyzer.validate_query_limits = Mock(
        return_value=["too complex"]
    )

    info = _make_info(
        operation_type="query",
        field_name="customers",
        operation_name="CustomerSearch",
    )

    result = middleware.resolve(lambda root, gql_info, **kwargs: "ok", None, info)

    assert result == "ok"
    middleware.complexity_analyzer.validate_query_limits.assert_not_called()


def test_query_limits_apply_to_listed_queries():
    with override_rail_settings(
        global_settings={
            "security_settings": {"limited_query_fields": ["CustomerSearch"]}
        }
    ):
        middleware = QueryComplexityMiddleware(schema_name="test")
        middleware.complexity_analyzer.validate_query_limits = Mock(
            return_value=["too complex"]
        )
        info = _make_info(
            operation_type="query",
            field_name="customers",
            operation_name="CustomerSearch",
        )

        with pytest.raises(ValueError, match="Query complexity validation failed"):
            middleware.resolve(lambda root, gql_info, **kwargs: "ok", None, info)

        middleware.complexity_analyzer.validate_query_limits.assert_called_once()
