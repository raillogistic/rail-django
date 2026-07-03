# Reporting & BI

Rail-Django provides persisted datasets, visualizations, reports, exports, and a
metadata-authorized report studio.

## Installation

Register the reusable GraphQL extensions:

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "query_extensions": [
            "rail_django.extensions.reporting.ReportingQuery",
        ],
        "mutation_extensions": [
            "rail_django.extensions.reporting.ReportingMutation",
        ],
    },
}

RAIL_DJANGO_REPORTING = {
    "viewer_roles": ["sales_viewer"],
    "author_roles": ["report_manager"],
    "admin_roles": ["report_manager"],
}
```

Models used as reporting sources should expose a scoped queryset:

```python
@staticmethod
def filter_reporting_queryset(queryset, user):
    return queryset.filter(organization=user.organization)
```

Studio datasets without that method are restricted to the current author's
reporting roles.

## Catalogs

Projects keep their domain definitions and synchronize them through the public
service:

```python
from rail_django.extensions.reporting import ReportingService

result = ReportingService.sync_catalog(
    DATASETS,
    VISUALIZATIONS,
    REPORTS,
    overwrite=True,
)
```

The safe default creates missing assets and skips existing ones. Pass
`overwrite=True` only when the project catalog is the source of truth.

Dataset definitions may declare `allowed_roles` directly. For older catalogs,
`metadata.allowed_roles` is migrated automatically. Reports may also declare an
audience with `allowed_roles`; access requires both report and dataset access.

## Runtime API

The public Python API is `ReportingService`:

- `list_reports(context)`
- `build_report_payload(context, report_code, filters={})`
- `create_report_export(context, report_code, format_name="xlsx", filters={})`
- `execute_dataset`, `preview_dataset`, and `render_visualization`

Report filters are an allowlist. Multi-dataset filters declare a target per
dataset and Rail-Django maps runtime values to the correct ORM field; unknown
filter names are rejected.

The corresponding GraphQL fields are:

```graphql
query Reports {
  reportingReportList
  reportingExportJobList
}

mutation Build($code: String!, $filters: GenericScalar) {
  reportingReportBuildPayload(code: $code, filters: $filters) {
    status
    message
    data
  }
}
```

`GenericScalar` values are objects, not JSON-encoded strings.

## Report Studio

`ReportingStudioService` validates every source model and field against the
Rail-Django metadata visible to the current user. It exposes dataset,
visualization, and report preview/save/delete operations. Catalog assets can be
edited but cannot be deleted through the studio; studio assets record their
creator and last editor.

Reusable GraphQL fields use the `reportingStudio*` prefix, including
`reportingStudioCapabilities`, asset lists, and preview/save/delete mutations.

## Exports

CSV and XLSX exports select the first table/records block, falling back to the
first block. Export jobs are always assigned to the requesting user and job
queries are owner-scoped. Available formats depend on installed renderer extras.
