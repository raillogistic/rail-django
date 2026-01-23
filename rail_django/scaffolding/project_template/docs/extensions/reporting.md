# Reporting & BI

## Overview

Rail Django includes a reporting and business intelligence module for defining analytical datasets, dimensions, metrics, and visualizations. This guide covers configuration, dataset definition, and GraphQL API usage.

---

## Table of Contents

1. [Concepts](#concepts)
2. [Dataset Definition](#dataset-definition)
3. [Dimensions](#dimensions)
4. [Metrics](#metrics)
5. [Query Execution](#query-execution)
6. [Visualizations](#visualizations)
7. [Reports](#reports)
8. [GraphQL API](#graphql-api)
9. [Best Practices](#best-practices)

---

## Concepts

### Key Components

| Component     | Description                                     |
| ------------- | ----------------------------------------------- |
| **Dataset**   | Data source (model or custom query)             |
| **Dimension** | Grouping attribute (category, date, status)     |
| **Metric**    | Aggregated measure (sum, count, average)        |
| **Filter**    | Constraints on the data                         |
| **Report**    | Saved combination of queries and visualizations |

---

## Dataset Definition

### Model-Based Dataset

```python
# apps/store/reporting.py
from rail_django.extensions.reporting import ReportingDataset

class OrderDataset(ReportingDataset):
    """
    Dataset for order analysis.
    """
    name = "orders"
    source_model = "store.Order"
    description = "Order analysis and metrics"

    # Base filters (always applied)
    base_filters = {
        "status__in": ["completed", "shipped"],
    }

    # Date field for time analysis
    date_field = "created_at"

    # Allowed aggregation period
    time_granularities = ["day", "week", "month", "quarter", "year"]
```

### Database Registration

```python
# Create via admin or management command
from rail_django.extensions.reporting import ReportingDataset

ReportingDataset.objects.create(
    code="monthly_sales",
    source_app_label="store",
    source_model="Order",
    dimensions=[
        {"field": "created_at", "transform": "trunc:month"},
        {"field": "category__name"},
    ],
    metrics=[
        {"field": "total", "aggregation": "sum", "name": "revenue"},
        {"field": "id", "aggregation": "count", "name": "order_count"},
    ],
)
```

---

## Dimensions

### Available Dimensions

| Type      | Example                    | Description        |
| --------- | -------------------------- | ------------------ |
| Field     | `"customer__name"`         | Direct field value |
| Date Part | `"created_at:month"`       | Date component     |
| Bucket    | `"price:bucket:0,100,500"` | Numeric ranges     |
| Custom    | `"custom:region_group"`    | Custom function    |

### Dimension Configuration

```python
class OrderDataset(ReportingDataset):
    dimensions = [
        # Simple field
        {
            "name": "category",
            "field": "product__category__name",
            "label": "Product Category",
        },
        # Date truncation
        {
            "name": "month",
            "field": "created_at",
            "transform": "trunc:month",
            "label": "Month",
        },
        # Numeric buckets
        {
            "name": "order_size",
            "field": "total",
            "transform": "bucket",
            "buckets": [0, 100, 500, 1000, 5000],
            "labels": ["Small", "Medium", "Large", "XL", "Enterprise"],
        },
        # Boolean
        {
            "name": "is_priority",
            "field": "priority",
            "label": "Priority Order",
        },
    ]
```

### Date Transformations

| Transform       | Example Output |
| --------------- | -------------- |
| `trunc:day`     | `2026-01-16`   |
| `trunc:week`    | `2026-W03`     |
| `trunc:month`   | `2026-01`      |
| `trunc:quarter` | `2026-Q1`      |
| `trunc:year`    | `2026`         |
| `extract:dow`   | `4` (Thursday) |
| `extract:hour`  | `14`           |

---

## Metrics

### Available Aggregations

| Aggregation | Description              |
| ----------- | ------------------------ |
| `count`     | Record count             |
| `sum`       | Sum of values            |
| `avg`       | Average                  |
| `min`       | Minimum                  |
| `max`       | Maximum                  |
| `stddev`    | Standard deviation       |
| `variance`  | Variance                 |
| `distinct`  | Count of distinct values |

### Metric Configuration

```python
class OrderDataset(ReportingDataset):
    metrics = [
        # Simple count
        {
            "name": "order_count",
            "aggregation": "count",
            "label": "Number of Orders",
        },
        # Sum with formatting
        {
            "name": "revenue",
            "field": "total",
            "aggregation": "sum",
            "label": "Total Revenue",
            "format": "currency",
            "currency": "USD",
        },
        # Average
        {
            "name": "avg_order_value",
            "field": "total",
            "aggregation": "avg",
            "label": "Average Order Value",
            "format": "currency",
        },
        # Calculated metric
        {
            "name": "conversion_rate",
            "expression": "completed_orders / total_orders * 100",
            "label": "Conversion Rate",
            "format": "percent",
        },
    ]
```

### Calculated Metrics

```python
{
    "name": "margin_percent",
    "expression": "(revenue - cost) / revenue * 100",
    "label": "Margin %",
    "format": "percent",
    "dependencies": ["revenue", "cost"],
}
```

---

## Query Execution

### GraphQL Query

```graphql
query OrderAnalysis(
  $dimensions: [String!]!
  $metrics: [String!]!
  $filters: ReportFilterInput
  $orderBy: String
  $limit: Int
) {
  reportQuery(
    dataset: "orders"
    dimensions: $dimensions
    metrics: $metrics
    filters: $filters
    orderBy: $orderBy
    limit: $limit
  ) {
    columns {
      name
      type
      label
    }
    rows {
      values
    }
    totals {
      metric
      value
    }
    metadata {
      rowCount
      executionTimeMs
    }
  }
}
```

### Variables

```json
{
  "dimensions": ["month", "category"],
  "metrics": ["revenue", "orderCount"],
  "filters": {
    "dateRange": {
      "field": "createdAt",
      "from": "2025-01-01",
      "to": "2025-12-31"
    },
    "conditions": [
      { "field": "status", "operator": "eq", "value": "completed" }
    ]
  },
  "orderBy": "-revenue",
  "limit": 100
}
```

### Response

```json
{
  "data": {
    "reportQuery": {
      "columns": [
        { "name": "month", "type": "date", "label": "Month" },
        { "name": "category", "type": "string", "label": "Category" },
        { "name": "revenue", "type": "currency", "label": "Revenue" },
        { "name": "orderCount", "type": "integer", "label": "Orders" }
      ],
      "rows": [
        { "values": ["2025-01", "Electronics", 125000.0, 450] },
        { "values": ["2025-01", "Clothing", 85000.0, 620] },
        { "values": ["2025-02", "Electronics", 142000.0, 510] }
      ],
      "totals": [
        { "metric": "revenue", "value": 352000.0 },
        { "metric": "orderCount", "value": 1580 }
      ],
      "metadata": {
        "rowCount": 3,
        "executionTimeMs": 125
      }
    }
  }
}
```

---

## Visualizations

### Chart Types

| Type      | Use Case                      |
| --------- | ----------------------------- |
| `bar`     | Category comparison           |
| `line`    | Trends over time              |
| `area`    | Cumulative trends             |
| `pie`     | Proportions                   |
| `donut`   | Proportions with center value |
| `table`   | Detailed data                 |
| `kpi`     | Single metric display         |
| `heatmap` | Two-dimensional comparison    |

### Visualization Configuration

```python
{
    "name": "revenue_by_month",
    "chart_type": "line",
    "dataset": "orders",
    "dimensions": ["month"],
    "metrics": ["revenue"],
    "options": {
        "show_legend": True,
        "show_data_labels": False,
        "colors": ["#4472C4"],
        "axis": {
            "x": {"label": "Month"},
            "y": {"label": "Revenue", "format": "currency"},
        },
    },
}
```

---

## Reports

### Report Definition

```python
from rail_django.extensions.reporting import Report

class MonthlySalesReport(Report):
    """
    Monthly sales report.
    """
    name = "monthly_sales"
    title = "Monthly Sales Report"
    description = "Sales analysis by month and category"

    # Datasets used
    datasets = ["orders", "products"]

    # Default filters
    default_filters = {
        "date_range": "last_12_months",
    }

    # Report sections
    sections = [
        {
            "title": "Summary",
            "widgets": [
                {"type": "kpi", "metric": "revenue", "label": "Total Revenue"},
                {"type": "kpi", "metric": "order_count", "label": "Orders"},
                {"type": "kpi", "metric": "avg_order_value", "label": "Avg. Order"},
            ],
        },
        {
            "title": "Trends",
            "widgets": [
                {
                    "type": "chart",
                    "chart_type": "line",
                    "dimensions": ["month"],
                    "metrics": ["revenue"],
                },
            ],
        },
        {
            "title": "By Category",
            "widgets": [
                {
                    "type": "chart",
                    "chart_type": "bar",
                    "dimensions": ["category"],
                    "metrics": ["revenue", "order_count"],
                },
            ],
        },
    ]
```

### Save Report

```graphql
mutation SaveReport($input: ReportInput!) {
  saveReport(input: $input) {
    ok
    report {
      id
      name
      createdAt
    }
  }
}
```

---

## GraphQL API

### List Datasets

```graphql
query AvailableDatasets {
  reportingDatasets {
    code
    name
    description
    dimensions {
      name
      label
      type
    }
    metrics {
      name
      label
      aggregation
    }
  }
}
```

### Execute Query

```graphql
query ExecuteReport($query: ReportQueryInput!) {
  reportQuery(query: $query) {
    columns {
      name
      type
    }
    rows {
      values
    }
  }
}
```

### List Saved Reports

```graphql
query MyReports {
  myReports {
    id
    name
    description
    createdAt
    updatedAt
  }
}
```

---

## Best Practices

### 1. Index Dimension Fields

```python
class Order(models.Model):
    created_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)

    class Meta:
        indexes = [
            models.Index(fields=["created_at", "status"]),
        ]
```

### 2. Use Materialized Views for Complex Reports

```python
# Create materialized view for heavy aggregations
from django.db import connection

def refresh_sales_summary():
    with connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW sales_summary")
```

### 3. Limit Results

```python
RAIL_DJANGO_REPORTING = {
    "max_rows": 10000,
    "default_limit": 1000,
    "query_timeout_seconds": 30,
}
```

### 4. Cache Expensive Queries

```python
from django.core.cache import cache

def get_cached_report(query_hash, execute_fn):
    cached = cache.get(f"report_{query_hash}")
    if cached:
        return cached

    result = execute_fn()
    cache.set(f"report_{query_hash}", result, timeout=300)
    return result
```

### 5. Monitor Query Performance

```python
RAIL_DJANGO_REPORTING = {
    "log_slow_queries": True,
    "slow_query_threshold_ms": 5000,
}
```

---

## See Also

- [Data Export](./exporting.md) - Export report results
- [PDF Generation](./templating.md) - Generate PDF reports
- [Observability](./observability.md) - Performance monitoring
