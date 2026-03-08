# Mutation and nested relation review report

This report summarizes the mutation and nested relation review completed on
March 8, 2026. The work focused on generated CRUD mutations, method-backed
mutations, nested relation handlers, and the generated form normalization path.
The result is a set of security, correctness, and contract-alignment fixes with
targeted regression coverage.

## Issues fixed

The review found concrete defects in authorization, nested relation error
handling, form normalization, and method-mutation naming.

- Enforced related-object access checks for nested `connect`, `disconnect`,
  `set`, and ID-based `update` flows in the shared nested relation handler.
- Returned field-specific validation errors when nested relation IDs do not
  resolve, instead of collapsing them into generic mutation failures.
- Added explicit protection for reverse-relation `disconnect` and `set`
  operations when the child foreign key is non-nullable.
- Restored required-field validation so it no longer skips required fields
  because of Django's `default` attribute, and extended that validation into
  nested `create` and `update` payloads.
- Kept `created_by` out of eager required-field validation because the mutation
  pipeline populates it later for authenticated callers.
- Aligned generated form relation normalization with the actual mutation
  contract:
  singular relations now normalize scalar IDs to scalar `connect` values,
  nested objects normalize to `create` or `update`, and to-many relation lists
  normalize into valid `connect`, `create`, and `update` operation groups.
- Rejected unsupported relation action names during normalization instead of
  silently treating arbitrary object keys as nested actions.
- Taught initial-data relation prefetch planning to honor camelCase
  `nestedFields`, which matches the public GraphQL API contract.
- Propagated `@custom_mutation_name(...)` into generated root mutation field
  names and metadata responses.
- Closed a method-mutation permission gap where explicit required permissions
  were bypassed when the GraphQL context had no authenticated `user`.

## Tests added and updated

The patch set adds focused regressions for the behaviors above so the reviewed
paths stay covered.

- Added mutation security tests for related-object retrieve and update guards in
  nested relation flows.
- Added regression coverage for field-specific invalid nested relation ID
  errors.
- Added recursive nested validation tests for reverse nested creates.
- Updated form normalization tests to cover singular and to-many relation
  shorthand, nested object normalization, and invalid singular list payloads.
- Added a camelCase `nestedFields` prefetch test.
- Added custom mutation name coverage for both generated mutation fields and
  metadata queries.

## Verification

The focused verification suite passed after the fixes:

```bash
pytest tests/unit/test_mutation_security.py \
  tests/unit/test_nested_operations.py \
  tests/unit/extensions/form/test_form_automation_and_coercion.py \
  tests/unit/test_form_extractor.py \
  tests/unit/test_naming_contract.py \
  tests/integration/test_model_schema_query.py \
  tests/integration/test_unified_mutations.py \
  tests/integration/test_model_form_nested_graphql_crud.py \
  tests/integration/extensions/form/test_model_form_contract_queries.py \
  tests/integration/extensions/form/test_model_form_mutation_contract.py -q
```

That command completed with `89 passed`.

## Next steps

If you want broader confidence, run the full mutation, form, and metadata test
slices in CI so the new nested authorization and normalization rules exercise a
wider set of model combinations.
