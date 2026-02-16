# Model detail v2 contract

This document defines the backend metadata contract used by
`ModelDetailV2`/`DynamicDetail` and how action, permission, and relation
metadata is resolved.

## Query shape

The detail contract entry point is:

```graphql
query ModelDetailContract($input: DetailContractInputType!) {
  modelDetailContract(input: $input) {
    ok
    reason
    contract { ... }
  }
}
```

`ok = false` is returned for fail-closed access decisions. In denied states, the
response includes `reason = "Access denied"` and no readable payload is exposed.

## Contract sections

The contract includes:

- Model identity: `appLabel`, `modelName`, `queryRoot`, `identifierArg`.
- Layout: `layoutNodes` with ordered sections/tabs/tables.
- Relations: `relationDataSources` with lazy/pagination metadata.
- Permissions: `permissions` snapshot for fail-closed filtering.
- Actions: `actions` plus scoped node actions.

## Action metadata and execution planning

Action definitions are extracted from canonical model mutations and expose:

- `key`, `label`, `scope`.
- `mutationName`.
- `inputTemplate`.
- `allowed` and `reason`.
- `auditEnabled`.

Runtime helpers in `detail_actions.py` provide:

- Template binding (`bind_action_template`).
- Permission-gated mutation selection (`resolve_detail_action_execution`).
- Audit emission for allowed/denied paths (`execute_detail_action`,
  `emit_action_audit_event`).

## Relation guards and pagination metadata

`detail_extractor.py` adds guard metadata per relation source:

- `max_depth`.
- `cycle_guard_enabled`.
- `cycle_detected`.
- `guard_path`.

For list sources, pagination metadata also includes:

- `page_arg` (`page`).
- `per_page_arg` (`perPage`).
- `default_per_page`.

## Validation

Run these commands from `rail-django`:

```bash
ruff check rail_django/extensions/metadata
pytest tests/integration/extensions/metadata -q
pytest tests/unit/extensions/metadata -q
```
