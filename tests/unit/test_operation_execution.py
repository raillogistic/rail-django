"""Operation planning must preserve authorization and field-level error payloads."""

from types import SimpleNamespace as NS
from unittest.mock import Mock

import graphene
import pytest
from graphql import ExecutionContext, GraphQLError

from rail_django.core.execution import RailExecutionContext
from rail_django.core.middleware.performance import QueryComplexityMiddleware
from rail_django.testing import override_rail_settings

pytestmark = pytest.mark.unit


def make_schema():
    """Return fields with visible resolver execution for denial assertions."""
    calls = []

    class Query(graphene.ObjectType):
        protected = graphene.String()
        public = graphene.String()

        def resolve_protected(root, info):
            calls.append("protected")
            return "Allowed"

        def resolve_public(root, info):
            calls.append("public")
            return "Public"

    return graphene.Schema(query=Query), calls


def test_limits_validate_once_and_keep_mixed_field_errors_identical():
    with override_rail_settings(
        global_settings={"security_settings": {"limited_query_fields": ["protected"]}}
    ):
        schema, calls = make_schema()
        checker = QueryComplexityMiddleware("operation_test")
        checker.complexity_analyzer.validate_query_limits = Mock(
            return_value=["Too complex"]
        )
        query = "{ first:protected second:protected public }"
        legacy = schema.execute(
            query,
            context_value=NS(),
            middleware=[checker],
            execution_context_class=ExecutionContext,
        )
        assert checker.complexity_analyzer.validate_query_limits.call_count == 2
        checker.complexity_analyzer.validate_query_limits.reset_mock()
        current = schema.execute(
            query,
            context_value=NS(),
            middleware=[checker],
            execution_context_class=RailExecutionContext,
        )
        assert checker.complexity_analyzer.validate_query_limits.call_count == 1
        assert (
            current.data
            == legacy.data
            == {"first": None, "second": None, "public": "Public"}
        )
        assert [error.formatted for error in current.errors] == [
            error.formatted for error in legacy.errors
        ]
        assert calls == ["public", "public"]


def test_execution_does_not_reuse_validation_between_operations():
    with override_rail_settings(
        global_settings={"security_settings": {"limited_query_fields": ["protected"]}}
    ):
        schema, calls = make_schema()
        checker = QueryComplexityMiddleware("operation_fresh_test")
        checker.complexity_analyzer.validate_query_limits = Mock(
            side_effect=[[], ["Denied now"]]
        )
        first = schema.execute(
            "{protected}",
            context_value=NS(),
            middleware=[checker],
            execution_context_class=RailExecutionContext,
        )
        second = schema.execute(
            "{protected}",
            context_value=NS(),
            middleware=[checker],
            execution_context_class=RailExecutionContext,
        )
        assert first.data == {"protected": "Allowed"}
        assert second.data == {"protected": None}
        assert second.errors
        assert calls == ["protected"]


def test_fragments_directives_and_unhashable_field_middleware_remain_enforced():
    class FieldGuard:
        __hash__ = None

        def resolve(self, next_resolver, root, info, **kwargs):
            if info.field_name == "protected":
                raise GraphQLError("Field denied")
            return next_resolver(root, info, **kwargs)

    with override_rail_settings(
        global_settings={"security_settings": {"limited_query_fields": ["protected"]}}
    ):
        schema, calls = make_schema()
        checker = QueryComplexityMiddleware("operation_directives_test")
        checker.complexity_analyzer.validate_query_limits = Mock(return_value=[])
        query = "query Test($show:Boolean!) {...Fields} fragment Fields on Query {protected @include(if:$show) public}"
        hidden = schema.execute(
            query,
            variable_values={"show": False},
            context_value=NS(),
            middleware=[checker, FieldGuard()],
            execution_context_class=RailExecutionContext,
        )
        assert hidden.data == {"public": "Public"}
        checker.complexity_analyzer.validate_query_limits.assert_not_called()
        denied = schema.execute(
            query,
            variable_values={"show": True},
            context_value=NS(),
            middleware=[checker, FieldGuard()],
            execution_context_class=RailExecutionContext,
        )
        assert denied.data == {"protected": None, "public": "Public"}
        assert denied.errors[0].message == "Field denied"
        assert "protected" not in calls
        checker.complexity_analyzer.validate_query_limits.assert_called_once()


def test_view_default_and_explicit_execution_context_contract():
    from rail_django.graphql.views.multi_schema import MultiSchemaGraphQLView

    schema, _ = make_schema()
    assert (
        MultiSchemaGraphQLView(schema=schema).execution_context_class
        is RailExecutionContext
    )

    class CustomContext(ExecutionContext):
        pass

    assert (
        MultiSchemaGraphQLView(
            schema=schema, execution_context_class=CustomContext
        ).execution_context_class
        is CustomContext
    )

    class CustomView(MultiSchemaGraphQLView):
        execution_context_class = CustomContext

    assert CustomView(schema=schema).execution_context_class is CustomContext


def test_real_complexity_rejection_matches_legacy_and_records_metrics():
    with override_rail_settings(
        global_settings={
            "security_settings": {"limited_query_fields": ["protected"]},
            "performance_settings": {
                "enable_query_cost_analysis": True,
                "max_query_complexity": 1,
            },
        }
    ):
        schema, calls = make_schema()
        checker = QueryComplexityMiddleware("operation_real_limits")
        query = "{ first:protected second:protected public }"
        outcomes = []
        for execution_context in (ExecutionContext, RailExecutionContext):
            metrics = NS()
            outcomes.append(
                schema.execute(
                    query,
                    context_value=NS(_graphql_metrics=metrics),
                    middleware=[checker],
                    execution_context_class=execution_context,
                )
            )
            assert metrics.query_complexity > 1
            assert metrics.query_depth == 1
        legacy, current = outcomes
        assert (
            current.data
            == legacy.data
            == {
                "first": None,
                "second": None,
                "public": "Public",
            }
        )
        assert [error.formatted for error in current.errors] == [
            error.formatted for error in legacy.errors
        ]
        assert calls == ["public", "public"]
