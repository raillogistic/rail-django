"""SQL work must follow selected model fields without weakening access checks."""

from types import SimpleNamespace as NS

import graphene
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rail_django.core.settings import QueryGeneratorSettings
from rail_django.generators.queries import QueryGenerator
from rail_django.generators.types import TypeGenerator
from test_app.models import Category, Post, Tag

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def query_schema():
    category = Category.objects.create(name="Category")
    tag = Tag.objects.create(name="Tag")
    for index in range(20):
        post = Post.objects.create(title=f"Post {index}", category=category)
        post.tags.add(tag)
    types = TypeGenerator(schema_name="performance_regression")
    types.generate_object_type(Category)
    types.generate_object_type(Tag)
    generator = QueryGenerator(
        types,
        settings=QueryGeneratorSettings(require_model_permissions=False),
        schema_name="performance_regression",
    )
    post_type = types.generate_object_type(Post)
    post_type._meta.fields["summary"] = graphene.Field(
        graphene.String, resolver=lambda obj, info: obj.title
    )

    class Query(graphene.ObjectType):
        page = generator.generate_paginated_query(Post)
        post = generator.generate_single_query(Post)

    return graphene.Schema(query=Query), post.pk


def execute_counted(schema, query, variables=None, *, superuser=True):
    """Count SQL including deferred reads during GraphQL serialization."""
    context = NS(
        schema_name="performance_regression",
        user=NS(is_authenticated=True, is_superuser=superuser),
        META={},
    )
    with CaptureQueriesContext(connection) as capture:
        result = schema.execute(query, variable_values=variables, context_value=context)
    assert not result.errors, result.errors
    return result.data, len(capture)


@pytest.mark.parametrize("superuser", [True, False])
@pytest.mark.parametrize("page_info", ["", "pageInfo { hasNextPage }"])
def test_items_only_and_ordinary_users_keep_relation_query_count_bounded(
    query_schema, page_info, superuser
):
    schema, _ = query_schema
    data, count = execute_counted(
        schema,
        "{ page(perPage:10, skipCount:true) { items { title category { name } tags { name } } "
        + page_info
        + " } }",
        superuser=superuser,
    )
    assert len(data["page"]["items"]) == 10
    assert count == 2


def test_aliases_fragments_and_directives_plan_only_selected_relations(query_schema):
    schema, _ = query_schema
    query = """
        query Test($tags: Boolean!) {
          renamed: page(perPage:10, skipCount:true) {
            rows: items { ...PostFields }
          }
        }
        fragment PostFields on PostType {
          title category { name } tags @include(if: $tags) { name }
        }
    """
    data, count = execute_counted(schema, query, {"tags": False})
    assert "tags" not in data["renamed"]["rows"][0]
    assert count == 1
    _, count = execute_counted(schema, query, {"tags": True})
    assert count == 2


def test_computed_field_does_not_defer_its_unknown_dependencies(query_schema):
    schema, _ = query_schema
    data, count = execute_counted(
        schema, "{ page(perPage:10, skipCount:true) { items { summary } } }"
    )
    assert len(data["page"]["items"]) == 10
    assert count == 1


@pytest.mark.parametrize("size", [10, 100])
def test_reverse_set_batches_reads_and_preserves_save_signals(size):
    from django.db.models.signals import post_save
    from rail_django.generators.nested.handler import NestedOperationHandlerBase
    from rail_django.testing import override_rail_settings
    from test_app.models import Product

    parent = Category.objects.create(name="Parent")
    Product.objects.bulk_create(
        [
            Product(name=f"Child {index}", price=1, category=parent)
            for index in range(size)
        ]
    )
    saved = []

    def receiver(sender, instance, **kwargs):
        saved.append(instance.pk)

    post_save.connect(receiver, sender=Product, weak=False)
    try:
        with override_rail_settings(
            global_settings={"security_settings": {"enable_abac": False}}
        ):
            handler = NestedOperationHandlerBase()
            info = NS(
                context=NS(user=NS(is_authenticated=True, has_perm=lambda p: True))
            )
            with CaptureQueriesContext(connection) as capture:
                handler.handle_set(parent, "products", [], info, False, True)
        reads = [
            q
            for q in capture
            if q["sql"].lstrip().upper().startswith("SELECT")
            and 'FROM "test_app_product"' in q["sql"]
        ]
        assert len(reads) == 2
        assert len(saved) == size
        assert Product.objects.filter(category=parent).count() == 0
    finally:
        post_save.disconnect(receiver, sender=Product)


def test_batched_set_denial_and_tenant_scope_leave_all_children_unchanged(monkeypatch):
    from graphql import GraphQLError
    from django.core.exceptions import ValidationError
    from rail_django.generators.nested.handler import NestedOperationHandlerBase
    from test_app.models import Product

    parent = Category.objects.create(name="Parent")
    children = Product.objects.bulk_create(
        [Product(name=f"Child {i}", price=1, category=parent) for i in range(3)]
    )
    handler = NestedOperationHandlerBase()
    checked = []

    def guard(model, operation, info, instance):
        checked.append(instance.pk)
        if len(checked) == 2:
            raise GraphQLError("Denied child")

    monkeypatch.setattr(handler, "_ensure_operation_access", guard)
    with pytest.raises(GraphQLError, match="Denied child"):
        handler.handle_set(parent, "products", [], None, False, True)
    assert Product.objects.filter(category=parent).count() == 3
    monkeypatch.setattr(handler, "_ensure_operation_access", lambda *a, **kw: None)
    monkeypatch.setattr(
        handler,
        "_get_tenant_queryset",
        lambda *a, **kw: Product.objects.exclude(pk=children[1].pk),
    )
    with pytest.raises(ValidationError, match="does not exist"):
        handler.handle_set(parent, "products", [], None, False, True)
    assert Product.objects.filter(category=parent).count() == 3


def test_batched_set_validation_failure_rolls_back_and_suppresses_commit_callbacks(
    monkeypatch, django_capture_on_commit_callbacks
):
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from django.db.models.signals import post_save
    from rail_django.generators.nested.handler import NestedOperationHandlerBase
    from test_app.models import Product

    parent = Category.objects.create(name="Parent")
    Product.objects.bulk_create(
        [Product(name=f"Child {i}", price=1, category=parent) for i in range(3)]
    )
    original = Product.full_clean
    validated, committed = [], []

    def validate(instance, *args, **kwargs):
        validated.append(instance.pk)
        if len(validated) == 2:
            raise ValidationError("Later validation failed")
        return original(instance, *args, **kwargs)

    def receiver(sender, instance, **kwargs):
        transaction.on_commit(lambda: committed.append(instance.pk))

    monkeypatch.setattr(Product, "full_clean", validate)
    post_save.connect(receiver, sender=Product, weak=False)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            with pytest.raises(ValidationError, match="Later validation failed"):
                NestedOperationHandlerBase().handle_set(
                    parent, "products", [], None, False, True
                )
        assert Product.objects.filter(category=parent).count() == 3
        assert committed == []
    finally:
        post_save.disconnect(receiver, sender=Product)


def test_related_lookup_override_and_duplicate_ids_keep_independent_instances(
    monkeypatch,
):
    from rail_django.generators.nested.handler import NestedOperationHandlerBase

    child = Category.objects.create(name="Related")
    handler = NestedOperationHandlerBase()
    resolved = handler._resolve_related_instances(
        field_name="related",
        related_model=Category,
        pks=[child.pk, child.pk],
        info=None,
        operation="retrieve",
    )
    assert resolved[0] is not resolved[1]
    calls = []

    def custom(**kwargs):
        calls.append(kwargs["pk"])
        return child

    monkeypatch.setattr(handler, "_resolve_related_instance", custom)
    assert handler._resolve_related_instances(
        field_name="related",
        related_model=Category,
        pks=[child.pk],
        info=None,
        operation="retrieve",
    ) == [child]
    assert calls == [child.pk]


def test_single_query_eager_loads_selected_relations(query_schema):
    schema, pk = query_schema
    data, count = execute_counted(
        schema, f'{{ post(id:"{pk}") {{ title category {{ name }} tags {{ name }} }} }}'
    )
    assert data["post"]["category"]["name"] == "Category"
    assert count == 2


def test_mutation_output_loading_keeps_saved_instance_and_unsaved_hook_values():
    from rail_django.generators.mutations.utils import _resolve_mutation_output

    category = Category.objects.create(name="Category")
    tag = Tag.objects.create(name="Tag")
    original = Post.objects.create(title="Saved", category=category)
    original.tags.add(tag)
    instance = Post.objects.get(pk=original.pk)
    instance.title = "Response hook value"
    types = TypeGenerator(schema_name="performance_regression")
    types.generate_object_type(Category)
    types.generate_object_type(Tag)

    class Payload(graphene.ObjectType):
        model_class = Post
        object = graphene.Field(
            types.generate_object_type(Post), resolver=_resolve_mutation_output
        )

    class Query(graphene.ObjectType):
        payload = graphene.Field(
            Payload, resolver=lambda root, info: Payload(object=instance)
        )

    data, count = execute_counted(
        graphene.Schema(query=Query),
        "{ payload { object { title category { name } tags { name } } } }",
    )
    assert data["payload"]["object"]["title"] == "Response hook value"
    assert instance.title == "Response hook value"
    assert Post.objects.get(pk=original.pk).title == "Saved"
    assert count == 2


def test_bulk_update_output_loads_relations_together_and_keeps_validation(monkeypatch):
    from graphql_relay import to_global_id
    from rail_django.core.settings import MutationGeneratorSettings
    from rail_django.generators.mutations import MutationGenerator
    from rail_django.testing import override_rail_settings

    category = Category.objects.create(name="Category")
    tag = Tag.objects.create(name="Tag")
    posts = Post.objects.bulk_create(
        [Post(title=f"Before {i}", category=category) for i in range(10)]
    )
    Post.tags.through.objects.bulk_create(
        [Post.tags.through(post_id=post.pk, tag_id=tag.pk) for post in posts]
    )
    validated = []
    original = Post.full_clean

    def validate(instance, *args, **kwargs):
        validated.append(instance.pk)
        return original(instance, *args, **kwargs)

    monkeypatch.setattr(Post, "full_clean", validate)
    with override_rail_settings(
        global_settings={"security_settings": {"enable_abac": False}}
    ):
        types = TypeGenerator(schema_name="performance_regression")
        types.generate_object_type(Category)
        types.generate_object_type(Tag)
        generator = MutationGenerator(
            types,
            MutationGeneratorSettings(require_model_permissions=False),
            schema_name="performance_regression",
        )

        class Query(graphene.ObjectType):
            ping = graphene.String()

        class Mutation(graphene.ObjectType):
            update = generator.generate_bulk_update_mutation(Post).Field()

        schema = graphene.Schema(query=Query, mutation=Mutation)
        inputs = ",".join(
            '{id:"' + to_global_id("PostType", post.pk) + '",data:{title:"After"}}'
            for post in posts
        )
        data, count = execute_counted(
            schema,
            "mutation { update(inputs:["
            + inputs
            + "]) { ok objects { title category { name } tags { name } } } }",
        )
    assert data["update"]["ok"]
    assert len(data["update"]["objects"]) == 10
    assert len(validated) == 10
    assert count < 40


def test_prefetched_nested_fields_still_apply_tenant_scope():
    from rail_django.testing import override_rail_settings
    from tests.models import TenantOrganization, TenantProject

    org_a = TenantOrganization.objects.create(name="A")
    org_b = TenantOrganization.objects.create(name="B")
    TenantProject.objects.create(name="Private A", organization=org_a)
    TenantProject.objects.create(name="Private B", organization=org_b)
    name = "tenant_performance"
    config = {
        name: {
            "multitenancy_settings": {
                "enabled": True,
                "default_tenant_field": "organization",
                "allow_cross_tenant_superuser": False,
            }
        }
    }
    with override_rail_settings(schema_settings=config):
        types = TypeGenerator(schema_name=name)
        types.generate_object_type(TenantOrganization)
        types.generate_object_type(TenantProject)
        generator = QueryGenerator(
            types,
            QueryGeneratorSettings(require_model_permissions=False),
            schema_name=name,
        )

        class Query(graphene.ObjectType):
            organizations = generator.generate_list_query(TenantOrganization)

        schema = graphene.Schema(query=Query)
        context = NS(
            schema_name=name,
            tenant_id=org_a.pk,
            user=NS(is_authenticated=True, is_superuser=True),
            META={},
        )
        result = schema.execute(
            "{ organizations { name projects { name } } }", context_value=context
        )
        assert not result.errors, result.errors
        by_name = {org["name"]: org["projects"] for org in result.data["organizations"]}
        assert by_name["A"] == [{"name": "Private A"}]
        assert by_name["B"] == []


def test_metadata_only_count_preserves_exact_totals_and_page_clamping(query_schema):
    schema, _ = query_schema
    data, count = execute_counted(
        schema,
        '{ page(page:999, perPage:10, countMode:"exact") { pageInfo { totalCount pageCount currentPage hasNextPage } } }',
    )
    assert data["page"]["pageInfo"] == {
        "totalCount": 20,
        "pageCount": 2,
        "currentPage": 2,
        "hasNextPage": False,
    }
    assert count == 1


def test_metadata_only_skip_count_and_typename_selections(query_schema):
    schema, _ = query_schema
    data, count = execute_counted(
        schema, "{ page(perPage:10, skipCount:true) { pageInfo { hasNextPage } } }"
    )
    assert data["page"]["pageInfo"]["hasNextPage"] is True
    assert count == 1
    data, count = execute_counted(
        schema, "{ page(perPage:10, skipCount:true) { items { __typename } } }"
    )
    assert len(data["page"]["items"]) == 10
    assert count == 1


def test_property_ordering_keeps_cap_without_count_or_deferred_reads(monkeypatch):
    from rail_django.generators.introspector import ModelIntrospector

    category = Category.objects.create(name="Category")
    Post.objects.bulk_create(
        [Post(title=f"Post {i}", category=category) for i in range(20)]
    )

    def sort_key(instance) -> str:
        return instance.title.lower()

    monkeypatch.setattr(Post, "sort_key", property(sort_key), raising=False)
    ModelIntrospector.clear_cache()
    try:
        types = TypeGenerator(schema_name="performance_regression")
        types.generate_object_type(Category)
        generator = QueryGenerator(
            types,
            QueryGeneratorSettings(
                require_model_permissions=False, max_property_ordering_results=5
            ),
            schema_name="performance_regression",
        )

        class Query(graphene.ObjectType):
            posts = generator.generate_list_query(Post)

        schema = graphene.Schema(query=Query)
        data, count = execute_counted(
            schema, '{ posts(limit:2, orderBy:["id", "-sort_key"]) { title } }'
        )
        assert data["posts"] == [{"title": "Post 4"}, {"title": "Post 3"}]
        assert count == 1
    finally:
        ModelIntrospector.clear_cache()
