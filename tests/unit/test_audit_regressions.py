"""Regressions for the security and lifecycle boundaries identified in the audit."""

import importlib
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import graphene
import pytest
from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.test import RequestFactory
from graphql import GraphQLError

from test_app.models import Category, Product
from rail_django.core.settings import MutationGeneratorSettings, QueryGeneratorSettings
from rail_django.generators.types import TypeGenerator
from rail_django.generators.queries import QueryGenerator
from rail_django.generators.mutations import MutationGenerator

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_discovery_imports_fresh_schema_module(tmp_path, monkeypatch):
    from rail_django.core.registry.discovery import _discover_app_schemas

    pkg = tmp_path / "audit_app"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "schema.py").write_text('SCHEMA_CONFIG = {"name": "audit_discovered"}')
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = Mock()
    _discover_app_schemas(registry, NS(name="audit_app"))
    assert registry.register_schema.call_count == 1
    importlib.import_module("audit_app.schema")
    _discover_app_schemas(registry, NS(name="audit_app"))
    assert registry.register_schema.call_count == 2


def test_database_discovery_catches_lazy_exception():
    from rail_django.core.registry.discovery import _register_schemas_from_database

    class LazyRows:
        def __iter__(self):
            raise OperationalError("synthetic missing table")

    model = NS(objects=NS(all=lambda: LazyRows()))
    with patch(
        "rail_django.core.registry.discovery.apps.get_model", return_value=model
    ):
        assert _register_schemas_from_database(Mock()) == 0


def test_cache_settings_do_not_bypass_resolver_permissions(monkeypatch):
    from rail_django.extensions.optimization.decorators import optimize_query
    from rail_django.extensions.query_cache import InMemoryQueryCacheBackend

    backend = InMemoryQueryCacheBackend()
    optimizer = NS(
        config=NS(
            enable_query_caching=True,
            query_cache_user_specific=False,
            query_cache_scope="schema",
        )
    )
    monkeypatch.setattr(
        "rail_django.extensions.optimization.decorators.get_optimizer",
        lambda *a: optimizer,
    )
    monkeypatch.setattr(
        "rail_django.extensions.optimization.decorators.get_performance_monitor",
        lambda *a: Mock(),
    )
    monkeypatch.setattr(
        "rail_django.core.services.get_query_cache_backend", lambda *a: backend
    )
    calls = []

    class Query(graphene.ObjectType):
        secret = graphene.String(value=graphene.String())

        @optimize_query()
        def resolve_secret(root, info, value):
            calls.append(value)
            if not info.context.user.allowed:
                raise GraphQLError("denied")
            return value

    schema = graphene.Schema(query=Query)
    admin = NS(
        schema_name="audit_cache", user=NS(id=1, is_authenticated=True, allowed=True)
    )
    denied = NS(
        schema_name="audit_cache", user=NS(id=2, is_authenticated=True, allowed=False)
    )
    a = schema.execute(
        '{ a: secret(value:"A") b: secret(value:"B") }', context_value=admin
    )
    assert a.errors is None and a.data == {"a": "A", "b": "B"}
    b = schema.execute(
        '{ a: secret(value:"A") b: secret(value:"B") }', context_value=denied
    )
    assert b.errors and b.data == {"a": None, "b": None}
    assert calls == ["A", "B", "A", "B"]
    backend._store.clear()
    x = schema.execute('{ secret(value:"A") }', context_value=admin)
    y = schema.execute('{ secret(value:"B") }', context_value=admin)
    assert x.data == {"secret": "A"} and y.data == {"secret": "B"}


def test_private_saved_filter_id_is_inaccessible():
    from rail_django.extensions.filters.models import SavedFilter
    from rail_django.generators.queries.base import QueryFilterPipeline

    owner = get_user_model().objects.create_user(username="audit_owner")
    stranger = get_user_model().objects.create_user(username="audit_stranger")
    saved = SavedFilter.objects.create(
        name="private_rule",
        model_name="Product",
        filter_json={"name": {"eq": "A"}},
        created_by=owner,
        is_shared=False,
    )
    pipeline = QueryFilterPipeline(
        NS(model=Product, info=NS(context=NS(user=stranger)))
    )
    assert pipeline._load_saved_filter("private_rule") is None
    assert pipeline._load_saved_filter(str(saved.pk)) is None


def test_reverse_set_requires_child_permission():
    from rail_django.testing import override_rail_settings

    with override_rail_settings(
        global_settings={"security_settings": {"enable_abac": False}}
    ):
        category = Category.objects.create(name="Parent")
        child = Product.objects.create(name="Child", price=1, category=category)
        user = NS(
            is_authenticated=True,
            is_superuser=False,
            has_perm=lambda p: p == "test_app.change_category",
        )
        info = NS(context=NS(user=user, META={}))
        ms = MutationGeneratorSettings()
        generator = MutationGenerator(TypeGenerator(mutation_settings=ms), settings=ms)
        mutation = generator.generate_update_mutation(Category)
        denied = mutation.mutate(
            None,
            info,
            id=str(category.pk),
            input={"products": {"disconnect": [str(child.pk)]}},
        )
        assert not denied.ok
        child.refresh_from_db()
        assert child.category_id == category.pk
        allowed = mutation.mutate(
            None, info, id=str(category.pk), input={"products": {"set": []}}
        )
        assert not allowed.ok
        child.refresh_from_db()
        assert child.category_id == category.pk
        user.has_perm = lambda permission: True
        permitted = mutation.mutate(
            None, info, id=str(category.pk), input={"products": {"set": []}}
        )
        assert permitted.ok, permitted.errors
        child.refresh_from_db()
        assert child.category_id is None


def test_csrf_rejects_fake_bearer_with_existing_session():
    from rail_django.utils.csrf import enforce_csrf_for_session_auth
    from rail_django.http.api.views.base import BaseAPIView

    request = RequestFactory().post(
        "/api/v1/management/", data="{}", content_type="application/json"
    )
    request.user = NS(is_authenticated=True)
    assert enforce_csrf_for_session_auth(request).status_code == 403
    request.META["HTTP_AUTHORIZATION"] = "Bearer definitely-invalid"
    assert BaseAPIView()._authenticate_request(request) is None
    assert enforce_csrf_for_session_auth(request).status_code == 403


@pytest.mark.parametrize("pagination", [False, True])
def test_database_error_fails_without_broadening_scope(monkeypatch, pagination):
    Product.objects.create(name="visible", price=1)
    Product.objects.create(name="hidden", price=2)
    generator = QueryGenerator(
        TypeGenerator(),
        settings=QueryGeneratorSettings(
            enable_pagination=pagination, require_model_permissions=False
        ),
    )
    monkeypatch.setattr(
        generator.optimizer,
        "optimize_queryset",
        lambda qs, *a: qs.prefetch_related("category").extra(
            select={"bad": "audit_missing_column"}
        ),
    )
    field = generator.generate_list_query(Product)

    class Query(graphene.ObjectType):
        products = field

    schema = graphene.Schema(query=Query)
    ctx = NS(
        schema_name="default",
        user=NS(is_authenticated=True, is_superuser=True),
        META={},
    )
    result = schema.execute(
        '{ products(where:{name:{eq:"visible"}}) { name } }', context_value=ctx
    )
    assert result.errors
    assert result.data["products"] is None
    assert "audit_missing_column" not in str(result.errors)


def test_aborted_custom_pipeline_rolls_back_write():
    from rail_django.generators.pipeline.base import MutationStep, MutationPipeline
    from rail_django.generators.pipeline.factories.base import BasePipelineMutation

    class WriteThenReject(MutationStep):
        order = 80
        name = "write_then_reject"

        def execute(self, ctx):
            ctx.result = Category.objects.create(name="should_rollback")
            ctx.add_error("Synthetic business rule rejected")
            return ctx

    class Rejected(BasePipelineMutation):
        model_class = Category
        operation = "create"
        pipeline = MutationPipeline([WriteThenReject()])

        @classmethod
        def build_response(cls, ctx):
            return cls(ok=not ctx.should_abort, errors=ctx.errors)

    response = Rejected.mutate(None, NS(context=NS(user=None)), input={})
    assert response.ok is False
    assert not Category.objects.filter(name="should_rollback").exists()


def test_tenant_header_requires_membership():
    from tests.unit.test_multitenancy import TestMultiTenancy

    case = TestMultiTenancy()
    case.setUp()
    query = "{ tenantProjectList { name } }"
    a = case._client(case.org1.id).execute(query)
    b = case._client(case.org2.id).execute(query)
    assert a["data"]["tenantProjectList"] == [{"name": "Project 1"}]
    assert b["errors"]


def test_registry_reregister_invalidates_compiled_schema():
    from rail_django.core.registry import SchemaRegistry

    registry = SchemaRegistry()
    registry.register_schema(
        "audit_reregister",
        apps=["test_app"],
        models=["test_app.Category"],
        auto_discover=False,
    )
    first = registry.get_schema_instance("audit_reregister")
    registry.register_schema(
        "audit_reregister",
        apps=["test_app"],
        models=["test_app.Product"],
        auto_discover=False,
    )
    second = registry.get_schema_instance("audit_reregister")
    assert first is not second
    registry.clear()


def test_query_count_baseline():
    import json, time, statistics
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from test_app.models import Tag, Post

    categories = [Category.objects.create(name=f"Cat {i}") for i in range(10)]
    tags = [Tag.objects.create(name=f"Tag {i}") for i in range(3)]
    for i in range(100):
        product = Post.objects.create(title=f"Post {i}", category=categories[i % 10])
        product.tags.add(tags[i % 3])
    generator = QueryGenerator(
        TypeGenerator(),
        settings=QueryGeneratorSettings(
            default_page_size=50, max_page_size=100, require_model_permissions=False
        ),
        schema_name="audit_perf",
    )

    class Query(graphene.ObjectType):
        products = generator.generate_list_query(Post)

    schema = graphene.Schema(query=Query)
    query = "{ products(limit:50) { title category { name } tags { name } } }"
    measures = []
    for i in range(6):
        ctx = NS(
            schema_name="audit_perf",
            user=NS(is_authenticated=True, is_superuser=True),
            META={},
        )
        start = time.perf_counter()
        with CaptureQueriesContext(connection) as capture:
            result = schema.execute(query, context_value=ctx)
        assert not result.errors, result.errors
        assert len(result.data["products"]) == 50
        measures.append(
            {
                "ms": round((time.perf_counter() - start) * 1000, 3),
                "queries": len(capture),
            }
        )

    assert all(measure["queries"] == 2 for measure in measures)
    print("Related-list benchmark:", measures)
