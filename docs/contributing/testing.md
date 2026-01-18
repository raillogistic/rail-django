# Testing Strategy

This document describes a safe, repeatable testing strategy for rail-django and
the helpers available in `rail_django.testing`.

## Goals

- Catch security and correctness regressions early.
- Keep the test suite fast enough for daily iteration.
- Provide clear coverage for core GraphQL generation, security, and performance.

## Test Pyramid

1. Unit tests (fast, no DB):
   - Settings resolution, error handling, and query analysis.
   - Type/query/mutation generators with lightweight model fixtures.
2. Integration tests (DB + Django):
   - Schema build, query execution, mutation workflows.
   - Middleware behavior, security controls, and auth flows.
3. Contract/regression tests:
   - Introspection snapshots and schema change tracking.
   - Known security edge cases (depth, complexity, input validation).

## What to Cover

- Schema build flow: discovery, registry, schema settings overrides.
- Query generation: filters, ordering, pagination, grouping.
- Mutation generation: validation, nested ops, error mapping.
- Security: auth, RBAC, field masking, input validation, rate limiting.
- Performance: optimizer hooks, query complexity, dataloader behavior.
- Error handling: correct mapping of Django and GraphQL errors.

## Using the Testing Module

The `rail_django.testing` package provides:

- `build_schema(...)` to build a schema with a local registry.
- `RailGraphQLTestClient` to execute GraphQL queries with a request context.
- `build_request(...)` and `build_context(...)` for middleware-compatible contexts.
- `override_rail_settings(...)` to isolate settings in a test scope.

Example:

```python
from rail_django.testing import build_schema, RailGraphQLTestClient

schema_harness = build_schema(schema_name="test", apps=["myapp"])
client = RailGraphQLTestClient(schema_harness.schema, schema_name="test")

result = client.execute(
    "query { health { status } }"
)
assert "errors" not in result
```

`RailGraphQLTestClient.execute(...)` accepts an optional `middleware` list so
you can exercise GraphQL middleware in unit tests.

Tip: use `override_rail_settings(...)` around schema creation if you want to
avoid persistent changes to `RAIL_DJANGO_GRAPHQL_SCHEMAS` during tests.
Speed tip: register a schema with explicit `apps`/`models` (even for the
`default` schema) so schema builds and snapshots avoid scanning all installed
apps.

## Organization and Markers

- `rail_django/tests/unit`: pure unit tests, no DB.
- `rail_django/tests/integration`: DB and schema execution tests.
- Use pytest markers: `@pytest.mark.unit`, `@pytest.mark.integration`.
  Pytest defaults to `rail_django.conf.test_settings`, which uses SQLite via
  `rail_django/conf/framework_settings.py`. Override `DJANGO_SETTINGS_MODULE` if
  you need another database backend.

## Test status

See CI for the latest test results.

## Full test inventory

This is the full map of every test module and its focus.

### Unit tests

- `rail_django/tests/unit/test_auth_decorators.py`: JWT view decorators, optional auth, permission enforcement.
- `rail_django/tests/unit/test_decorators.py`: schema registration decorators and mutation/business decorator metadata.
- `rail_django/tests/unit/test_exporting.py`: ModelExporter allowlists, formula sanitization, field formatters, filter and ordering validation, csv/xlsx outputs.
- `rail_django/tests/unit/test_field_permissions.py`: field masking, field permission decorator, visible fields for users.
- `rail_django/tests/unit/test_filters.py`: filter set generation, complex filter input shape, complex filter application.
- `rail_django/tests/unit/test_generators.py`: type generation mapping, relationships, caching, invalid model errors.
- `rail_django/tests/unit/test_introspector.py`: field/relationship introspection, choices, properties, validation (includes skips).
- `rail_django/tests/unit/test_metadata_schema.py`: metadata extraction, permissions, GraphQL metadata query integration.
- `rail_django/tests/unit/test_mfa.py`: MFA manager fingerprint and SMS token flow (stubbed devices).
- `rail_django/tests/unit/test_mutations.py`: mutation generation, input types, relationship handling, error paths.
- `rail_django/tests/unit/test_observability.py`: Sentry and OpenTelemetry plugin hooks.
- `rail_django/tests/unit/test_performance_metrics.py`: metrics collector frequency stats and distributions.
- `rail_django/tests/unit/test_permissions.py`: permission checkers, permission query, permission filter mixin, decorator behavior.
- `rail_django/tests/unit/test_phase0_regressions.py`: regression coverage for error handling, masking, complexity.
- `rail_django/tests/unit/test_phase4_performance.py`: query cache hit/invalidation, user-specific cache, query metrics collector.
- `rail_django/tests/unit/test_phase5_security.py`: access guard auth/introspection, validation severity, audit redaction, auth cookies.
- `rail_django/tests/unit/test_phase6_persisted_queries.py`: persisted query allowlist, hash mismatch, allow-unregistered flows.
- `rail_django/tests/unit/test_phase6_plugins.py`: plugin hook interception.
- `rail_django/tests/unit/test_queries.py`: query generation for single/list/nested cases and invalid model handling.
- `rail_django/tests/unit/test_query_cache_extension.py`: in-memory cache expiry and version bumps.
- `rail_django/tests/unit/test_rate_limiting_extension.py`: rate limiting middleware allow/block/login scope.
- `rail_django/tests/unit/test_rbac.py`: role assignment, permission checks, role/permission decorators.
- `rail_django/tests/unit/test_registry.py`: schema registry lifecycle and discovery helpers.
- `rail_django/tests/unit/test_reporting.py`: reporting helper safety (formula eval, identifiers, hashing, filter normalization).
- `rail_django/tests/unit/test_required_relationships.py`: required relationship fields in input generation.
- `rail_django/tests/unit/test_subscriptions.py`: subscription consumer dependency handling.
- `rail_django/tests/unit/test_templating.py`: template registry, access checks, PDF rendering, preview view.
- `rail_django/tests/unit/test_validation_extension.py`: validation query for field checks.
- `rail_django/tests/unit/test_virus_scanner.py`: mock scanner clean vs threat, quarantine list/delete.

### Integration tests

run using integration tests using .venv311\Scripts\python with DJANGO_SETTINGS_MODULE=rail_django.conf.test_settings

- `rail_django/tests/integration/test_api_endpoints.py`: API endpoints for GraphQL/REST, auth/permissions, rate limiting, CORS, batching, subscriptions (contains skips where features are toggled off).
- `rail_django/tests/integration/test_database_operations.py`: CRUD operations, relationships, transactions, constraints, concurrency, validation.
- `rail_django/tests/integration/test_export_view.py`: export endpoint CSV response with JWT auth and allowlists.
- `rail_django/tests/integration/test_filters_pagination_mutations.py`: quick and complex filtering, list and paginated queries, CRUD mutations, nested tags, error paths.
- `rail_django/tests/integration/test_multi_schema.py`: multi-schema routing, schema list URLs, auth gating.
- `rail_django/tests/integration/test_phase5_security.py`: refresh token reuse detection and audit retention cleanup.
- `rail_django/tests/integration/test_phase6_schema_registry.py`: schema registry snapshots, export, diff endpoints.
- `rail_django/tests/integration/test_reporting_engine.py`: reporting dataset execution in records mode.
- `rail_django/tests/integration/test_rest_api.py`: schema management REST API list/detail/create/update/delete, discovery, health/metrics, CORS, errors.
- `rail_django/tests/integration/test_schema_generation.py`: schema build, introspection, query/mutation execution, filtering/pagination, error handling, concurrency/perf (business method mutation remains skipped).

### Health system tests

- `rail_django/tests/test_health_system.py`: health checks, metrics, dashboard/API endpoints, caching, load/perf behaviors.

## Running Tests

```bash
pytest -m unit
pytest -m integration
pytest -m "not integration"
```

For the Django test runner (used in CI):

```bash
DJANGO_SETTINGS_MODULE=rail_django.conf.framework_settings \
python -m django test rail_django.tests.unit
```

Lint check used in CI:

```bash
python -m black --check rail_django/testing rail_django/tests/unit/test_phase0_regressions.py
```

## Regression Checklist (before release)

- Run unit + integration tests.
- Validate schema build in production settings (no debug fields).
- Verify security limits (depth/complexity/introspection).
