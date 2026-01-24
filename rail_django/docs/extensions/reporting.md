# Reporting & BI

Rail Django includes a reporting and business intelligence module for defining analytical datasets, dimensions, metrics, and visualizations directly on top of your Django models.

## Overview

The reporting extension allows you to:
- Define **Datasets** as data sources (models or custom queries).
- Configure **Dimensions** for grouping (by date, category, status, etc.).
- Define **Metrics** for aggregation (sum, count, average, etc.).
- Execute high-performance analytical queries via GraphQL.
- Define **Visualizations** (charts, KPIs, tables).
- Create and save **Reports** combining multiple widgets.

## Dataset Definition

A dataset is the source of truth for your analytical queries.

```python
from rail_django.extensions.reporting import ReportingDataset

class OrderDataset(ReportingDataset):
    name = "orders"
    source_model = "store.Order"
    description = "Order analysis and metrics"

    # Base filters always applied to this dataset
    base_filters = {
        "status__in": ["completed", "shipped"],
    }

    # Date field used for time-based analysis
    date_field = "created_at"
```

## Dimensions

Dimensions are the attributes you use to group your data.

| Type | Example | Description |
|------|---------|-------------|
| **Field** | `"customer__name"` | Direct value from a model field. |
| **Date Part** | `"created_at:month"` | Truncated date (day, week, month, year). |
| **Bucket** | `"price:bucket:0,100,500"` | Numeric ranges for distribution analysis. |

### Date Transformations

| Transform | Output Example |
|-----------|----------------|
| `trunc:day` | `2026-01-16` |
| `trunc:month` | `2026-01` |
| `extract:dow` | `4` (Thursday) |

## Metrics

Metrics are the aggregated measures of your data.

| Aggregation | Description |
|-------------|-------------|
| `count` | Record count. |
| `sum` | Sum of numeric values. |
| `avg` | Arithmetic mean. |
| `distinct` | Count of unique values. |

### Calculated Metrics
You can define metrics that depend on other metrics:
```python
{
    "name": "margin_percent",
    "expression": "(revenue - cost) / revenue * 100",
    "label": "Margin %",
    "format": "percent",
}
```

## GraphQL API

### Available Datasets
Query the registry to see what's available for reporting:

```graphql
query AvailableDatasets {
  reportingDatasets {
    code
    name
    dimensions { name label type }
    metrics { name label aggregation }
  }
}
```

### Executing a Report Query
Use the `reportQuery` to fetch aggregated data:

```graphql
query SalesByCategory {
  reportQuery(
    dataset: "orders"
    dimensions: ["category"]
    metrics: ["revenue", "orderCount"]
    orderBy: "-revenue"
  ) {
    columns { name type label }
    rows { values }
    totals { metric value }
  }
}
```

## Visualizations & Reports

You can combine queries into structured reports with various visualization types:
- **Charts**: Bar, Line, Area, Pie, Donut, Heatmap.
- **KPIs**: Single big numbers for key indicators.
- **Tables**: Detailed aggregated data.

## Best Practices

1. **Database Indexing**: Always index fields used as dimensions, especially date fields.
2. **Limit Results**: Use the `limit` argument to prevent huge result sets from hitting the frontend.
3. **Caching**: Analytical queries can be heavy. Use Rail's query caching or external caching for frequently accessed reports.
4. **Materialized Views**: For extremely large datasets, consider using database materialized views as the source for your datasets.

## See Also

- [Exporting](./exporting.md) - To download report data as Excel/CSV.
- [Templating](./templating.md) - To generate PDF reports.
- [Observability](./observability.md) - To monitor query performance.
