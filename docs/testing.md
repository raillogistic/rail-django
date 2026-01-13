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

## Test coverage map
This is a quick reference for what each test module is responsible for.

### Unit tests (1)
- `rail_django/tests/unit/test_decorators.py`: schema registration decorators, mutation/business decorators, logging.
- `rail_django/tests/unit/test_generators.py`: type generation mapping, relationships, caching, meta handling, invalid model errors.
- `rail_django/tests/unit/test_introspector.py`: model field/relationship introspection, validation, choices, dataclasses, multi-model workflow.
- `rail_django/tests/unit/test_metadata_schema.py`: metadata extraction, permissions, GraphQL query integration, edge cases.
- `rail_django/tests/unit/test_mutations.py`: mutation generation, input types, relationship handling, validation/error paths, performance.

### Unit tests (2)
- `rail_django/tests/unit/test_phase0_regressions.py`: error handling mapping, field masking, complexity enforcement, schema override handling.
- `rail_django/tests/unit/test_phase4_performance.py`: query cache hit/invalidation, user-specific cache, metrics collector.
- `rail_django/tests/unit/test_phase5_security.py`: access guard auth/introspection, input validation severity, audit redaction, auth cookies.
- `rail_django/tests/unit/test_phase6_persisted_queries.py`: APQ allowlist enforcement, allow_unregistered registration, hash mismatch/not found flows.
- `rail_django/tests/unit/test_phase6_plugins.py`: plugin execution hook interception.

### Unit tests (3)
- `rail_django/tests/unit/test_queries.py`: query generation for single/list/nested cases and invalid model handling.
- `rail_django/tests/unit/test_registry.py`: schema registry lifecycle (register/enable/list/clear/discover) and global helpers.
- `rail_django/tests/unit/test_required_relationships.py`: required relationship fields in inputs across fk/o2o/m2m.
- `rail_django/tests/unit/test_templating.py`: pdf template registry inheritance and permission gating.

### Integration tests (1)
- `rail_django/tests/integration/test_api_endpoints.py`: endpoint availability, auth/permissions, validation, rate limiting, cors, batching, perf, headers.
- `rail_django/tests/integration/test_database_operations.py`: CRUD, relationships, business methods, transactions, constraints, concurrency, perf, migrations.
- `rail_django/tests/integration/test_multi_schema.py`: multi-schema routing, schema list urls, auth gating, error handling.
- `rail_django/tests/integration/test_phase5_security.py`: jwt refresh reuse detection, audit retention cleanup.
- `rail_django/tests/integration/test_phase6_schema_registry.py`: schema snapshot export, history, diff endpoints.

### Integration tests (2)
- `rail_django/tests/integration/test_rest_api.py`: schema management REST API list/detail/create/update/delete, discovery, health/metrics, cors, errors.
- `rail_django/tests/integration/test_schema_generation.py`: full schema build, introspection, query/mutation execution, filters/pagination, errors, concurrency, caching, extensions.

### Health system tests
- `rail_django/tests/test_health_system.py`: health checker, metrics, reporting, dashboard/api endpoints, integration load/perf/caching.

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
