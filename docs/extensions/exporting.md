# Exporting Extension

Module: `rail_django.extensions.exporting`

- `POST /api/v1/export/` exports CSV or XLSX.
- Default-deny export schema with allowlisted accessors and filters.
- Optional async export jobs with status/download URLs.
- Export URLs require JWT auth decorators to be installed.
- Export settings live in [reference/configuration](../reference/configuration.md).
