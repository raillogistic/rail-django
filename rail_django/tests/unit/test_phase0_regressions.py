"""
Targeted regression tests for Phase 0 stabilization.
"""

from types import SimpleNamespace

import graphene
from graphql import get_introspection_query, parse
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.test import TestCase

from rail_django.core.error_handling import ErrorHandler
from rail_django.extensions.optimization import optimize_query
from rail_django.generators.queries import QueryGenerator
from rail_django.generators.types import TypeGenerator
from rail_django.security.graphql import (
    GraphQLSecurityAnalyzer,
    SecurityConfig,
    create_security_middleware,
    security_analyzer,
)
from rail_django.testing import build_context, build_schema


class Phase0MaskingModel(models.Model):
    password = models.CharField(max_length=128)
    email = models.EmailField()

    class Meta:
        app_label = "phase0_tests"


class TestPhase0Regressions(TestCase):
    def _info_for_user(self, user):
        context = build_context(user=user, schema_name="phase0")
        return SimpleNamespace(context=context)

    def test_error_handler_maps_django_validation_error(self):
        handler = ErrorHandler()
        error = handler.handle_error(DjangoValidationError("invalid"))
        self.assertEqual(error.code, "VALIDATION_ERROR")

    def test_field_masking_authenticated_user_masks_sensitive_fields(self):
        generator = QueryGenerator(TypeGenerator())
        instance = Phase0MaskingModel(password="secret", email="user@example.com")
        info = self._info_for_user(User(username="tester"))

        masked = generator._apply_field_masks(instance, info, Phase0MaskingModel)

        self.assertNotEqual(masked.password, "secret")
        self.assertEqual(masked.email, "user@example.com")

    def test_field_masking_anonymous_user_masks_sensitive_fields(self):
        generator = QueryGenerator(TypeGenerator())
        instance = Phase0MaskingModel(password="secret", email="user@example.com")
        info = self._info_for_user(AnonymousUser())

        masked = generator._apply_field_masks(instance, info, Phase0MaskingModel)

        self.assertNotEqual(masked.password, "secret")

    def test_graphql_security_middleware_enforces_complexity_limits(self):
        class Query(graphene.ObjectType):
            first = graphene.String()
            second = graphene.String()

            def resolve_first(root, info):
                return "one"

            def resolve_second(root, info):
                return "two"

        schema = graphene.Schema(query=Query)
        middleware = [
            create_security_middleware(
                SecurityConfig(max_query_complexity=0)
            )
        ]
        context = build_context(schema_name="security")

        query = """
        query Test {
          ...Fields
        }
        fragment Fields on Query {
          first
          second
        }
        """

        result = schema.execute(
            query,
            context_value=context,
            middleware=middleware,
        )

        self.assertTrue(result.errors)
        self.assertIn("complex", result.errors[0].message.lower())

    def test_graphql_security_allows_introspection_depth(self):
        class Query(graphene.ObjectType):
            ping = graphene.String()

            def resolve_ping(root, info):
                return "pong"

        schema = graphene.Schema(query=Query)
        analyzer = GraphQLSecurityAnalyzer(
            SecurityConfig(
                max_query_depth=10,
                enable_introspection=True,
                enable_depth_limiting=True,
                enable_query_cost_analysis=False,
            )
        )
        document = parse(get_introspection_query())

        result = analyzer.analyze_query(document, schema.graphql_schema)

        self.assertTrue(result.has_introspection)
        self.assertTrue(result.introspection_only)
        self.assertFalse(
            any(
                "Profondeur" in reason or "depth" in reason
                for reason in result.blocked_reasons
            )
        )

    def test_schema_builder_respects_authentication_required_override(self):
        harness = build_schema(
            schema_name="phase0_auth",
            settings={"AUTHENTICATION_REQUIRED": False},
        )

        self.assertFalse(harness.builder.settings.authentication_required)

    def test_optimize_query_enforces_complexity_limit(self):
        class Query(graphene.ObjectType):
            echo = graphene.String()

            @optimize_query(complexity_limit=0)
            def resolve_echo(root, info):
                return "ok"

        schema = graphene.Schema(query=Query)
        context = build_context(schema_name="optimization")

        result = schema.execute(
            "{ echo }",
            context_value=context,
        )

        self.assertTrue(result.errors)
        self.assertIn("complexity", result.errors[0].message.lower())

