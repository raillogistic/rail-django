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
