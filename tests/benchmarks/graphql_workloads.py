"""Opt-in synthetic workloads; execute this file explicitly with pytest.

Set RAIL_PERF_OUTPUT_DIR to retain JSON results. Timing has no pass threshold.
The normal test suite does not collect this filename.
"""

import json
import os
import platform
import statistics
import time
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import django
import graphene
import graphql
import pytest
import rail_django
from django.db import connection, reset_queries
from django.test.utils import CaptureQueriesContext
from graphql_relay import to_global_id
from rail_django.core.settings import MutationGeneratorSettings, QueryGeneratorSettings
from rail_django.core.middleware.performance import QueryComplexityMiddleware
from rail_django.generators.mutations import MutationGenerator
from rail_django.generators.queries import QueryGenerator
from rail_django.generators.types import TypeGenerator
from rail_django.generators.introspector import ModelIntrospector
from rail_django.generators.nested.handler import NestedOperationHandlerBase
from rail_django.testing import override_rail_settings
from test_app.models import Category, Post, Tag, Product

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _record(output, workload):
    """Write reproducible observations, never benchmark credentials or row data."""
    expected = os.environ.get("RAIL_PERF_SOURCE_ROOT")
    if expected:
        assert (
            Path(rail_django.__file__)
            .resolve()
            .is_relative_to(Path(expected).resolve())
        )
    output.update(
        python=platform.python_version(),
        django=django.get_version(),
        graphql=graphql.__version__,
        database=connection.vendor,
        source=rail_django.__file__,
    )
    directory = os.environ.get("RAIL_PERF_OUTPUT_DIR")
    if directory:
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / (workload + ".json")).write_text(json.dumps(output, indent=2))
    print(json.dumps(output))


@pytest.mark.django_db
def test_reads():
    categories = Category.objects.bulk_create(
        [Category(name=f"Category {i}") for i in range(10)]
    )
    tags = Tag.objects.bulk_create([Tag(name=f"Tag {i}") for i in range(3)])
    posts = Post.objects.bulk_create(
        [Post(title=f"Post {i}", category=categories[i % 10]) for i in range(1000)]
    )
    Post.tags.through.objects.bulk_create(
        [
            Post.tags.through(post_id=p.pk, tag_id=tags[i % 3].pk)
            for i, p in enumerate(posts)
        ]
    )
    type_generator = TypeGenerator(schema_name="perf_bench")
    type_generator.generate_object_type(Category)
    type_generator.generate_object_type(Tag)
    generator = QueryGenerator(
        type_generator,
        settings=QueryGeneratorSettings(
            default_page_size=50, max_page_size=100, require_model_permissions=False
        ),
        schema_name="perf_bench",
    )

    class Query(graphene.ObjectType):
        posts = generator.generate_list_query(Post)
        page = generator.generate_paginated_query(Post)
        post = generator.generate_single_query(Post)

    schema = graphene.Schema(query=Query)
    fields = "title category { name } tags { name }"
    scenarios = {}
    for size in (10, 50):
        scenarios[f"list_{size}"] = f"{{ posts(limit:{size}) {{ {fields} }} }}"
        scenarios[f"page_items_{size}"] = (
            f"{{ page(perPage:{size}, skipCount:true) {{ items {{ {fields} }} }} }}"
        )
        scenarios[f"page_info_{size}"] = (
            f"{{ page(perPage:{size}, skipCount:true) {{ items {{ {fields} }} pageInfo {{ hasNextPage }} }} }}"
        )
    scenarios["single"] = f'{{ post(id:"{posts[0].pk}") {{ {fields} }} }}'
    output = {
        "label": os.environ.get("PERF_LABEL", "current"),
        "dataset": 1000,
        "samples": 30,
        "scenarios": {},
    }
    for label, query in scenarios.items():
        timings, counts = ([], [])
        for index in range(33):
            context = NS(
                schema_name="perf_bench",
                user=NS(is_authenticated=True, is_superuser=True),
                META={},
            )
            reset_queries()
            start = time.perf_counter()
            with CaptureQueriesContext(connection) as capture:
                result = schema.execute(query, context_value=context)
            elapsed = (time.perf_counter() - start) * 1000
            assert not result.errors, result.errors
            if index >= 3:
                timings.append(elapsed)
                counts.append(len(capture))
        output["scenarios"][label] = {
            "queries": sorted(set(counts)),
            "median_ms": round(statistics.median(timings), 3),
            "min_ms": round(min(timings), 3),
            "max_ms": round(max(timings), 3),
        }
    if os.environ.get("PERF_PROFILE"):
        import cProfile, pstats

        profiler = cProfile.Profile()
        profiler.enable()
        result = schema.execute(scenarios["list_50"], context_value=context)
        profiler.disable()
        pstats.Stats(profiler).sort_stats("cumulative").print_stats(35)
    _record(output, "reads")


@pytest.mark.django_db
def test_reverse_set():
    results = {}
    with override_rail_settings(
        global_settings={"security_settings": {"enable_abac": False}}
    ):
        info = NS(
            context=NS(
                user=NS(
                    is_authenticated=True, is_superuser=True, has_perm=lambda p: True
                ),
                META={},
            )
        )
        handler = NestedOperationHandlerBase()
        for size in (1, 10, 100):
            parent = Category.objects.create(name=f"Parent {size}")
            children = Product.objects.bulk_create(
                [
                    Product(name=f"Child {i}", price=1, category=parent)
                    for i in range(size)
                ]
            )
            ids = [child.pk for child in children]
            timings, counts = ([], [])
            for index in range(33):
                Product.objects.filter(pk__in=ids).update(category=parent)
                reset_queries()
                start = time.perf_counter()
                with CaptureQueriesContext(connection) as queries:
                    handler.handle_set(parent, "products", [], info, False, True)
                elapsed = (time.perf_counter() - start) * 1000
                assert not Product.objects.filter(pk__in=ids, category=parent).exists()
                if index >= 3:
                    timings.append(elapsed)
                    counts.append(len(queries))
            results[str(size)] = {
                "queries": sorted(set(counts)),
                "median_ms": round(statistics.median(timings), 3),
            }
    output = {
        "label": os.environ.get("PERF_LABEL", "current"),
        "samples": 30,
        "scenarios": results,
    }
    _record(output, "reverse-set")


@pytest.mark.django_db
def test_bulk_output():
    category = Category.objects.create(name="Category")
    tag = Tag.objects.create(name="Tag")
    posts = Post.objects.bulk_create(
        [Post(title=f"Post {i}", category=category) for i in range(50)]
    )
    Post.tags.through.objects.bulk_create(
        [Post.tags.through(post_id=p.pk, tag_id=tag.pk) for p in posts]
    )
    output = {
        "label": os.environ.get("PERF_LABEL", "current"),
        "samples": 30,
        "scenarios": {},
    }
    with override_rail_settings(
        global_settings={"security_settings": {"enable_abac": False}}
    ):
        types = TypeGenerator(schema_name="response_bench")
        types.generate_object_type(Category)
        types.generate_object_type(Tag)
        generator = MutationGenerator(
            types, MutationGeneratorSettings(), schema_name="response_bench"
        )

        class Query(graphene.ObjectType):
            ping = graphene.String()

        class Mutation(graphene.ObjectType):
            update = generator.generate_bulk_update_mutation(Post).Field()

        schema = graphene.Schema(query=Query, mutation=Mutation)
        for size in (10, 50):
            inputs = ",".join(
                (
                    '{id:"'
                    + to_global_id("PostType", p.pk)
                    + '",data:{title:"Updated"}}'
                    for p in posts[:size]
                )
            )
            query = (
                "mutation { update(inputs:["
                + inputs
                + "]) { ok errors { message } objects { title category {name} tags {name} } } }"
            )
            timings, counts = ([], [])
            for index in range(33):
                context = NS(
                    schema_name="response_bench",
                    user=NS(
                        is_authenticated=True,
                        is_superuser=True,
                        has_perm=lambda p: True,
                    ),
                    META={},
                )
                reset_queries()
                start = time.perf_counter()
                with CaptureQueriesContext(connection) as capture:
                    result = schema.execute(query, context_value=context)
                elapsed = (time.perf_counter() - start) * 1000
                assert not result.errors, result.errors
                assert result.data["update"]["ok"], result.data
                if index >= 3:
                    timings.append(elapsed)
                    counts.append(len(capture))
            output["scenarios"][str(size)] = {
                "queries": sorted(set(counts)),
                "median_ms": round(statistics.median(timings), 3),
            }
    _record(output, "bulk-output")


@pytest.mark.django_db
def test_pagination():
    category = Category.objects.create(name="Category")
    Post.objects.bulk_create(
        [Post(title=f"Post {i:04}", category=category) for i in range(200)]
    )

    def sort_key(self) -> str:
        return self.title.lower()

    output = {
        "label": os.environ.get("PERF_LABEL", "current"),
        "samples": 30,
        "scenarios": {},
    }
    with patch.object(Post, "sort_key", property(sort_key), create=True):
        ModelIntrospector.clear_cache()
        types = TypeGenerator(schema_name="pagination_bench")
        types.generate_object_type(Category)
        generator = QueryGenerator(
            types,
            QueryGeneratorSettings(
                require_model_permissions=False,
                max_property_ordering_results=100,
                property_ordering_warn_on_cap=False,
            ),
            schema_name="pagination_bench",
        )

        class Query(graphene.ObjectType):
            posts = generator.generate_list_query(Post)
            page = generator.generate_paginated_query(Post)

        schema = graphene.Schema(query=Query)
        scenarios = {
            "property_list": '{posts(limit:50,orderBy:["sort_key"]){id}}',
            "metadata_exact": "{page(perPage:50){pageInfo{totalCount hasNextPage}}}",
            "metadata_skip": "{page(perPage:50,skipCount:true){pageInfo{hasNextPage}}}",
        }
        for label, query in scenarios.items():
            timings, counts = ([], [])
            for index in range(33):
                context = NS(
                    schema_name="pagination_bench",
                    user=NS(is_authenticated=True, is_superuser=True),
                    META={},
                )
                reset_queries()
                start = time.perf_counter()
                with CaptureQueriesContext(connection) as capture:
                    result = schema.execute(query, context_value=context)
                elapsed = (time.perf_counter() - start) * 1000
                assert not result.errors, result.errors
                if index >= 3:
                    timings.append(elapsed)
                    counts.append(len(capture))
            output["scenarios"][label] = {
                "queries": sorted(set(counts)),
                "median_ms": round(statistics.median(timings), 3),
            }
    ModelIntrospector.clear_cache()
    _record(output, "pagination")


def test_operation_limits():
    try:
        from rail_django.core.execution import RailExecutionContext
    except ModuleNotFoundError:
        RailExecutionContext = None

    class Item(graphene.ObjectType):
        title = graphene.String()
        value = graphene.Int()

    class Query(graphene.ObjectType):
        records = graphene.List(Item)

        def resolve_records(root, info):
            return [{"title": "Row", "value": i} for i in range(3)]

    schema = graphene.Schema(query=Query)
    query = (
        "query Many { "
        + " ".join((f"a{i}:records{{title value}}" for i in range(20)))
        + " }"
    )
    settings = {
        "security_settings": {"limited_query_fields": ["records"]},
        "performance_settings": {
            "max_query_complexity": 100000,
            "max_query_depth": 50,
            "enable_query_cost_analysis": True,
        },
    }
    timings, counts = ([], [])
    with override_rail_settings(global_settings=settings):
        middleware = QueryComplexityMiddleware("execution_benchmark")
        original = middleware.complexity_analyzer.validate_query_limits
        for index in range(105):
            context = NS(
                schema_name="execution_benchmark",
                user=NS(is_authenticated=True, is_superuser=True),
            )
            with patch.object(
                middleware.complexity_analyzer, "validate_query_limits", wraps=original
            ) as validate:
                start = time.perf_counter()
                result = schema.execute(
                    query,
                    context_value=context,
                    middleware=[middleware],
                    execution_context_class=RailExecutionContext,
                )
                elapsed = (time.perf_counter() - start) * 1000
                assert not result.errors, result.errors
                if index >= 5:
                    timings.append(elapsed)
                    counts.append(validate.call_count)
    output = {
        "label": os.environ.get("PERF_LABEL", "current"),
        "samples": 100,
        "root_aliases": 20,
        "validation_calls": sorted(set(counts)),
        "median_ms": round(statistics.median(timings), 3),
    }
    _record(output, "operation-limits")
