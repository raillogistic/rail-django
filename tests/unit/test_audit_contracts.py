"""Compatibility and failure-mode regressions for the audit corrections."""

from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import graphene
import pytest
from django.db import OperationalError
from graphql import GraphQLError
from rail_django.testing import override_rail_settings, build_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_discovery_reports_dependency_failures(tmp_path, monkeypatch):
    from rail_django.core.registry.discovery import _discover_app_schemas

    pkg = tmp_path / "broken_audit_app"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "schemas.py").write_text("import missing_audit_dependency")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ModuleNotFoundError, match="missing_audit_dependency"):
        _discover_app_schemas(Mock(), NS(name="broken_audit_app"))


def test_required_database_registry_fails_closed(settings):
    from rail_django.core.registry.discovery import _register_schemas_from_database

    settings.RAIL_DJANGO_DATABASE_REGISTRY_REQUIRED = True
    model = NS(objects=NS(all=Mock(side_effect=OperationalError("missing registry"))))
    with patch(
        "rail_django.core.registry.discovery.apps.get_model", return_value=model
    ):
        with pytest.raises(OperationalError):
            _register_schemas_from_database(Mock())


def test_tenant_header_denied_without_authorizer_and_trusted_context_preserved():
    from rail_django.extensions.multitenancy.resolver import resolve_tenant_id

    config = {"tenant_secure": {"multitenancy_settings": {"enabled": True}}}
    with override_rail_settings(schema_settings=config):
        request = build_request(
            schema_name="tenant_secure", headers={"X-Tenant-ID": "other"}
        )
        request.user = NS(is_authenticated=True)
        with pytest.raises(GraphQLError, match="not authorized"):
            resolve_tenant_id(request, schema_name="tenant_secure")
        request.tenant_id = "trusted"
        assert resolve_tenant_id(request, schema_name="tenant_secure") == "trusted"


def test_registry_preserves_custom_mutations_and_builder_references():
    from rail_django.core.registry import SchemaRegistry

    class CustomMutation(graphene.Mutation):
        ok = graphene.Boolean()

        @classmethod
        def mutate(cls, root, info):
            return cls(ok=True)

    registry = SchemaRegistry()
    try:
        registry.register_schema(
            "audit_custom",
            apps=["test_app"],
            models=["test_app.Category"],
            auto_discover=False,
        )
        builder = registry.get_schema_builder("audit_custom")
        builder.register_mutation(CustomMutation, name="audit_custom_operation")
        assert builder.get_schema().graphql_schema.mutation_type.fields.get(
            "auditCustomOperation"
        )
        registry.register_schema(
            "audit_custom",
            apps=["test_app"],
            models=["test_app.Product"],
            auto_discover=False,
        )
        assert registry.get_schema_builder("audit_custom") is builder
        schema = registry.get_schema_instance("audit_custom")
        assert "auditCustomOperation" in schema.graphql_schema.mutation_type.fields
        assert "productList" in schema.graphql_schema.query_type.fields
        assert "categoryList" not in schema.graphql_schema.query_type.fields
    finally:
        registry.clear()


def test_revoked_socket_token_clears_trusted_claims():
    from rail_django.extensions.subscriptions.consumer import RailGraphqlWsConsumer

    consumer = RailGraphqlWsConsumer()
    consumer._token = "revoked"
    consumer._jwt_payload = {"tenant_id": "old-tenant"}
    with patch(
        "rail_django.extensions.auth.JWTManager.verify_token", return_value=None
    ):
        assert consumer._authenticated_user() is None
    assert consumer._jwt_payload == {}


def test_schema_cache_cannot_stamp_old_schema_with_concurrent_new_version():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock, RLock
    from rail_django.core.registry.builders import get_schema_instance

    old_schema, new_schema = object(), object()
    reader_ready, updated = Event(), Event()
    registry = NS(_lock=Lock(), _schema_instance_cache={})
    builder = NS(_lock=RLock(), _schema=old_schema, version=1)
    builder.get_schema_version = lambda: builder.version

    def get_schema():
        with builder._lock:
            schema = builder._schema
        reader_ready.set()
        updated.wait(timeout=0.5)
        return schema

    builder.get_schema = get_schema

    def update():
        assert reader_ready.wait(timeout=5)
        with builder._lock:
            builder._schema = new_schema
            builder.version = 2
            with registry._lock:
                registry._schema_instance_cache.clear()
        updated.set()

    with patch(
        "rail_django.core.registry.builders.get_schema_builder", return_value=builder
    ):
        with ThreadPoolExecutor(max_workers=2) as workers:
            reader = workers.submit(get_schema_instance, registry, "concurrent")
            writer = workers.submit(update)
            reader.result(timeout=5)
            writer.result(timeout=5)
        assert get_schema_instance(registry, "concurrent") is new_schema


def test_wkhtmltopdf_requires_opt_in_even_without_url_fetcher():
    from rail_django.extensions.templating.rendering.renderers import (
        WkhtmltopdfRenderer,
    )

    with patch(
        "rail_django.extensions.templating.rendering.renderers.shutil.which",
        return_value="wkhtmltopdf",
    ):
        with patch(
            "rail_django.extensions.templating.rendering.renderers.subprocess.run"
        ) as run:
            with pytest.raises(RuntimeError, match="cannot enforce"):
                WkhtmltopdfRenderer().render(
                    "<p>test</p>", base_url=None, url_fetcher=None, config={}
                )
            run.assert_not_called()


def test_subscription_snapshots_round_trip_through_wire_types():
    import json
    from datetime import datetime
    from django.contrib.auth import get_user_model
    from rail_django.extensions.subscriptions.broadcaster import _snapshot_instance
    from rail_django.generators.subscriptions.utils import _build_instance_from_payload

    model = get_user_model()
    user = model.objects.create_user(username="wire-snapshot")
    snapshot = json.loads(json.dumps(_snapshot_instance(user)))
    rebuilt = _build_instance_from_payload(model, {"snapshot": snapshot})
    assert rebuilt.pk == user.pk
    assert isinstance(rebuilt.date_joined, datetime)
    assert rebuilt.date_joined == user.date_joined
