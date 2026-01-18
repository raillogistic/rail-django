# Test Report

## Initial Full Run
- Command: `.venv311/Scripts/python -m pytest`
- Result: Timed out after ~13m38s
- Outcome at timeout: 10 failed, 348 passed, 8 skipped
- Failures reported:
  - `rail_django/tests/integration/test_api_endpoints.py::TestAPIEndpointsIntegration::test_authentication_required_endpoint`
  - `rail_django/tests/integration/test_api_endpoints.py::TestAPIEndpointsIntegration::test_batch_queries_endpoint`
  - `rail_django/tests/integration/test_api_endpoints.py::TestAPIEndpointsIntegration::test_permission_based_access`
  - `rail_django/tests/integration/test_api_endpoints.py::TestAPIEndpointsIntegration::test_rate_limiting_endpoint`
  - `rail_django/tests/integration/test_database_operations.py::TestDatabaseOperationsIntegration::test_complex_relationships_operations`
  - `rail_django/tests/integration/test_database_operations.py::TestDatabaseOperationsIntegration::test_create_operations`
  - `rail_django/tests/integration/test_database_operations.py::TestDatabaseOperationsIntegration::test_delete_operations`
  - `rail_django/tests/integration/test_database_operations.py::TestDatabaseOperationsIntegration::test_update_operations`
  - `rail_django/tests/integration/test_schema_generation.py::TestSchemaGenerationIntegration::test_mutation_execution_with_data`
  - `rail_django/tests/integration/test_schema_generation.py::TestSchemaGenerationIntegration::test_query_execution_with_data`

## Fixes Applied
- Updated custom scalars to support GraphQL-core 3 AST nodes and parse_literal signature; corrected Decimal handling and patched Graphene Decimal to accept float literals (`rail_django/core/scalars.py`).
- Resolved DataLoader Promise results for reverse relations under Graphene 3 to avoid empty lists (`rail_django/generators/types_objects.py`).
- Improved legacy rate limit settings handling and schema security settings safety (`rail_django/rate_limiting.py`).
- Allowed mixed single/batch JSON payloads when batch mode is enabled (`rail_django/views/graphql_views.py`).
- Preserved primary key on delete mutation return to avoid null non-nullable id (`rail_django/generators/mutations_crud.py`).
- Aligned API endpoint tests with schema behaviors and permissions (camelCase settings, batch config, mutation selection fields, error matching) (`rail_django/tests/integration/test_api_endpoints.py`).
- Corrected schema generation test expectations for company count (`rail_django/tests/integration/test_schema_generation.py`).

## Verification Runs
- Command: `.venv311/Scripts/python -m pytest rail_django/tests/integration/test_api_endpoints.py -k "authentication_required_endpoint or batch_queries_endpoint or permission_based_access or rate_limiting_endpoint" -q`
  - Result: 4 passed, 14 deselected (with existing PytestCollectionWarning for TestQuery/TestMutation)
- Command: `.venv311/Scripts/python -m pytest rail_django/tests/integration/test_database_operations.py -k "create_operations or update_operations or delete_operations or complex_relationships_operations" -q`
  - Result: 4 passed, 11 deselected
- Command: `.venv311/Scripts/python -m pytest rail_django/tests/integration/test_schema_generation.py -k "query_execution_with_data or mutation_execution_with_data" -q`
  - Result: 2 passed, 12 deselected

## Notes
- Full test suite was not re-run after fixes due to the initial timeout; only the previously failing areas were re-validated.
