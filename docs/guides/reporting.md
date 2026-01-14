# Reporting (BI) Guide

This guide covers how to define and query reporting datasets, build
visualizations, and generate report payloads.

## Overview

The reporting module is backed by Django models:

- `ReportingDataset`: defines a semantic layer over a Django model
- `ReportingVisualization`: saved chart/table definitions
- `ReportingReport`: a dashboard layout composed of visualizations
- `ReportingExportJob`: payload snapshots for PDF/CSV/JSON/XLSX exports

The GraphQL auto schema exposes method mutations for dataset preview/query and
for rendering visualizations/reports. You can also call these model methods
directly in Python.

## Defining a dataset

Datasets declare dimensions (group-by columns), metrics (aggregations), and
optional computed fields.

Example:

```python
from rail_django.extensions.reporting import ReportingDataset

dataset = ReportingDataset.objects.create(
    code="customers",
    title="Customers",
    source_app_label="tests",
    source_model="TestCustomer",
    dimensions=[
        {"name": "city", "field": "ville_client"},
        {"name": "created_month", "field": "created_at", "transform": "trunc:month"},
    ],
    metrics=[
        {"name": "total_customers", "field": "pk", "aggregation": "count"},
        {"name": "avg_balance", "field": "solde_compte", "aggregation": "avg"},
    ],
    computed_fields=[
        {"name": "avg_per_city", "formula": "avg_balance / total_customers"},
    ],
    default_filters=[
        {"field": "est_actif", "lookup": "exact", "value": True},
    ],
    metadata={
        "allow_ad_hoc": False,
        "allowed_fields": ["est_actif"],
        "record_fields": ["nom_client", "email_client", "ville_client"],
        "quick_fields": ["nom_client", "email_client"],
        "max_limit": 2000,
        "cache_ttl_seconds": 60,
    },
)
```

### Dimension transforms

Supported transforms include:

- `lower`, `upper`
- `date`
- `trunc:hour|day|week|month|quarter|year`
- `year|quarter|month|week|weekday|day` (extractors)

### Metric aggregations

Built-in aggregations:

- `count`, `distinct_count`, `sum`, `avg`, `min`, `max`

Postgres-only aggregations (supported when the DB vendor is PostgreSQL):

- `array_agg`, `string_agg`, `jsonb_agg`
- `bool_and`, `bool_or`
- `bit_and`, `bit_or`, `bit_xor`

You can pass metric options with `options`:

```python
{
  "name": "emails",
  "field": "email_client",
  "aggregation": "string_agg",
  "options": {"delimiter": "; ", "distinct": True, "ordering": ["email_client"]}
}
```

## Running a preview

Preview executes the dataset definition with optional runtime filters.

```python
payload = dataset.preview(
    quick="alpha",
    limit=50,
    ordering="-created_at",
    filters=[{"field": "ville_client", "lookup": "icontains", "value": "paris"}],
)
```

## Dynamic queries (`run_query`)

Dynamic queries support dimensions/metrics overrides, HAVING filters, ordering,
offset/limit, pivoting, and caching.

Aggregate mode (default):

```python
spec = {
    "dimensions": ["city"],
    "metrics": ["total_customers", "avg_balance"],
    "filters": [{"field": "est_actif", "lookup": "exact", "value": True}],
    "having": [{"field": "total_customers", "lookup": "gte", "value": 5}],
    "ordering": ["-total_customers"],
    "limit": 100,
    "offset": 0,
}
payload = dataset.run_query(spec)
```

Records mode:

```python
spec = {
    "mode": "records",
    "fields": ["nom_client", "email_client", "ville_client"],
    "ordering": ["-created_at"],
    "limit": 50,
}
payload = dataset.run_query(spec)
```

Notes:

- `default_filters` are always merged into `run_query`.
- Records mode fields are allowlisted by `metadata.record_fields` (or
  `metadata.fields`), plus `allow_ad_hoc` rules. See `../reference/security.md`.
- `limit=0` returns an empty result set; negative limits are ignored with a
  warning.

### Filter tree syntax

Filters can be a flat list:

```json
[
  {"field": "est_actif", "lookup": "exact", "value": true},
  {"field": "ville_client", "lookup": "icontains", "value": "paris"}
]
```

Or a tree with `items` and `op`:

```json
{
  "op": "and",
  "items": [
    {"field": "est_actif", "lookup": "exact", "value": true},
    {
      "op": "or",
      "items": [
        {"field": "ville_client", "lookup": "icontains", "value": "paris"},
        {"field": "ville_client", "lookup": "icontains", "value": "lyon"}
      ]
    }
  ]
}
```

## Visualizations

Visualizations store a frontend config plus an optional query spec:

```python
from rail_django.extensions.reporting import ReportingVisualization

viz = ReportingVisualization.objects.create(
    dataset=dataset,
    code="customers_by_city",
    title="Customers by city",
    kind="bar",
    config={
        "query": {
            "dimensions": ["city"],
            "metrics": ["total_customers"],
            "ordering": ["-total_customers"],
            "limit": 20,
        },
        "x_axis": "city",
        "y_axis": "total_customers",
    },
)

payload = viz.render(quick="", limit=200, filters=[])
```

## Reports

Reports aggregate multiple visualizations into a single payload:

```python
from rail_django.extensions.reporting import ReportingReport

report = ReportingReport.objects.create(code="overview", title="Overview")
payload = report.build_payload(quick="", limit=200, filters=[])
```

## Exports

Export jobs capture a snapshot payload for PDF/CSV/JSON/XLSX generation:

```python
from rail_django.extensions.reporting import ReportingExportJob

job = ReportingExportJob.objects.create(
    title="Customers export",
    dataset=dataset,
    format="csv",
)
job.run_export()
```

The payload is stored on the job for the frontend or a background worker to
render into a file.

## Security notes

See `../reference/security.md` for reporting allowlists, `record_fields`, and
`allow_ad_hoc` rules.
