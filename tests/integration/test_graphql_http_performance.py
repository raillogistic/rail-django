"""Real HTTP coverage and opt-in measurements for generated GraphQL operations."""

import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

import graphene
import pytest
import requests
import rail_django
from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import path
from graphql_relay import to_global_id

from rail_django.core.registry import schema_registry
from rail_django.core.settings import MutationGeneratorSettings, QueryGeneratorSettings
from rail_django.extensions.auth import JWTManager
from rail_django.generators.mutations import MutationGenerator
from rail_django.generators.queries import QueryGenerator
from rail_django.generators.types import TypeGenerator
from rail_django.graphql.views import MultiSchemaGraphQLView
from rail_django.testing import override_rail_settings
from test_app.models import Category, Post, Tag

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_generated_queries_mutations_and_denials_over_http(
    settings, request, monkeypatch
):
    """Use only synthetic test rows; timing is opt-in and has no flaky threshold."""
    name = "http_performance"
    expected_source = os.environ.get("RAIL_PERF_SOURCE_ROOT")
    if expected_source:
        assert (
            Path(rail_django.__file__)
            .resolve()
            .is_relative_to(Path(expected_source).resolve())
        )
    module = ModuleType("rail_http_performance_urls")

    class QueryCounter:
        def __init__(self, get_response):
            self.get_response = get_response

        def __call__(self, http_request):
            count, sql_seconds = 0, 0.0

            def execute(execute, sql, params, many, context):
                nonlocal count, sql_seconds
                start = time.perf_counter()
                try:
                    return execute(sql, params, many, context)
                finally:
                    count += 1
                    sql_seconds += time.perf_counter() - start

            with connection.execute_wrapper(execute):
                response = self.get_response(http_request)
            response["X-Test-Query-Count"] = str(count)
            response["X-Test-SQL-Ms"] = str(sql_seconds * 1000)
            return response

    module.QueryCounter = QueryCounter
    module.urlpatterns = [
        path("graphql/<str:schema_name>/", MultiSchemaGraphQLView.as_view())
    ]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    settings.ROOT_URLCONF = module.__name__
    settings.MIDDLEWARE = [module.__name__ + ".QueryCounter", *settings.MIDDLEWARE]
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}
    }
    settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
    settings.DEBUG = False
    global_config = {
        "middleware_settings": {
            "enable_rate_limiting_middleware": False,
            "log_queries": False,
            "log_mutations": False,
        },
        "security_settings": {"enable_abac": False, "enable_permission_cache": False},
    }
    config = {
        "schema_settings": {"authentication_required": True, "enable_graphiql": False},
        "multitenancy_settings": {"enabled": False},
        "performance_settings": {
            "enable_query_caching": False,
            "max_query_complexity": 100000,
        },
        "security_settings": {"limited_query_fields": ["page"]},
    }
    with override_rail_settings(
        global_settings=global_config, schema_settings={name: config}
    ):
        category = Category.objects.create(name="HTTP Category")
        tag = Tag.objects.create(name="HTTP Tag")
        posts = Post.objects.bulk_create(
            [Post(title=f"HTTP Post {i}", category=category) for i in range(1000)]
        )
        Post.tags.through.objects.bulk_create(
            [Post.tags.through(post_id=post.pk, tag_id=tag.pk) for post in posts]
        )
        types = TypeGenerator(schema_name=name)
        types.generate_object_type(Category)
        types.generate_object_type(Tag)
        queries = QueryGenerator(types, QueryGeneratorSettings(), schema_name=name)
        mutations = MutationGenerator(
            types, MutationGeneratorSettings(), schema_name=name
        )

        class Query(graphene.ObjectType):
            page = queries.generate_paginated_query(Post)

        class Mutation(graphene.ObjectType):
            update = mutations.generate_bulk_update_mutation(Post).Field()

        schema = graphene.Schema(query=Query, mutation=Mutation)
        schema_registry.register_schema(name, settings=config, auto_discover=False)
        builder = schema_registry.get_schema_builder(name)
        builder._schema = schema
        user = get_user_model().objects.create_superuser(
            username="http_performance_owner"
        )
        denied_user = get_user_model().objects.create_user(
            username="http_performance_denied"
        )
        token = JWTManager.generate_token(user)["token"]
        denied_token = JWTManager.generate_token(denied_user)["token"]
        server = request.getfixturevalue("live_server")
        endpoint = server.url + f"/graphql/{name}/"
        query = "{ page(perPage:50, skipCount:true) { items { title category { name } tags { name } } } }"

        def post(query_text, credential=token):
            started = time.perf_counter()
            with requests.Session() as client:
                client.trust_env = False
                response = client.post(
                    endpoint,
                    json={"query": query_text},
                    headers={"Authorization": f"Bearer {credential}"},
                    timeout=30,
                )
            elapsed = (time.perf_counter() - started) * 1000
            assert response.status_code == 200, response.text
            return (
                response.json(),
                elapsed,
                int(response.headers["X-Test-Query-Count"]),
                float(response.headers["X-Test-SQL-Ms"]),
            )

        try:
            data, _, _, _ = post(query)
            assert "errors" not in data, data
            assert len(data["data"]["page"]["items"]) == 50
            denied, _, _, _ = post(query, denied_token)
            assert denied.get("errors")
            assert denied.get("data", {}).get("page") is None
            inputs = ",".join(
                '{id:"'
                + to_global_id("PostType", post.pk)
                + '",data:{title:"HTTP Updated"}}'
                for post in posts[:10]
            )
            mutation = (
                "mutation { update(inputs:["
                + inputs
                + "]) { ok errors { message } objects { title category { name } tags { name } } } }"
            )
            updated, _, _, _ = post(mutation)
            assert not updated.get("errors"), updated
            assert updated["data"]["update"]["ok"], updated
            assert Post.objects.filter(title="HTTP Updated").count() == 10

            samples = int(os.environ.get("RAIL_PERF_HTTP_SAMPLES", "0"))
            if samples:
                results = {}
                for label, operation in (
                    ("page_50", query),
                    ("bulk_update_10", mutation),
                ):
                    for _ in range(3):
                        post(operation)
                    measures = [post(operation) for _ in range(samples)]
                    assert all(not value[0].get("errors") for value in measures)
                    results[label] = {
                        "median_ms": round(
                            statistics.median(value[1] for value in measures), 3
                        ),
                        "queries": sorted({value[2] for value in measures}),
                        "median_sql_ms": round(
                            statistics.median(value[3] for value in measures), 3
                        ),
                    }
                started = time.perf_counter()
                with ThreadPoolExecutor(max_workers=4) as workers:
                    concurrent = list(
                        workers.map(lambda _: post(query), range(samples))
                    )
                wall = time.perf_counter() - started
                assert all(not value[0].get("errors") for value in concurrent)
                results["four_clients"] = {
                    "requests": samples,
                    "wall_seconds": round(wall, 3),
                    "requests_per_second": round(samples / wall, 3),
                }
                output = {
                    "label": os.environ.get("PERF_LABEL", "current"),
                    "samples": samples,
                    "dataset": 1000,
                    "source": rail_django.__file__,
                    "scenarios": results,
                }
                Path(os.environ["RAIL_PERF_HTTP_OUTPUT"]).write_text(
                    json.dumps(output, indent=2)
                )
                print(json.dumps(output))
        finally:
            schema_registry.unregister_schema(name)
