# Importing Guide

For a detailed overview of the feature and its GraphQL API, see the [Data Importing Extension Documentation](../extensions/importing.md).

## Overview

`rail_django.extensions.importing` provides a template-driven import pipeline for ModelTable:

1. Resolve active template metadata (`modelImportTemplate`).
2. Upload CSV/XLSX and stage rows (`createModelImportBatch`).
3. Patch rows during review (`updateModelImportBatch` with `PATCH_ROWS`).
4. Validate dataset (`VALIDATE`) and run dry-run simulation (`SIMULATE`).
5. Commit atomically (`COMMIT`) or delete batch (`deleteModelImportBatch`).

## Limits

- Max rows per batch: `10,000` (default, configurable via template metadata).
- Max upload size: `25 MB` (default, configurable via template metadata).
- Accepted formats: `CSV`, `XLSX`.

## Data Model

- `ImportBatch`: lifecycle and summary counters.
- `ImportRow`: staged editable row payload.
- `ImportIssue`: parse/edit/validate/simulate/commit issues.
- `ImportSimulationSnapshot`: latest simulation summary for commit gating.

## Extension Wiring

The extension is integrated by default in schema mixins:

- Query integration: `ImportQuery`
- Mutation integration: `ImportMutations`

No additional manual schema registration is required.

## Operational Notes

- Version enforcement is strict: `templateVersion` must exactly match active template.
- Duplicate matching keys are blocking validation errors.
- Commits are atomic; failures produce zero writes.
- Error reports are generated as CSV files in `MEDIA_ROOT/import-reports` (or temp dir fallback).

## Testing

Run import-specific tests:

```bash
cd rail-django
pytest tests/integration -k model_import -q
pytest tests/unit -k import_services -q
```
