# 5 Enterprise Features Roadmap

This document outlines five high-impact enterprise features recommended for implementation in `rail-django`. These features address common gaps in enterprise GraphQL APIs and align with industry standards (Hasura, PostGraphile, Apollo Federation).

---

## 1. Multi-Tenancy Extension

**Module:** `rail_django.extensions.multitenancy`  
**Priority:** Critical for SaaS applications

### Problem

No built-in support for tenant data isolation. Multi-tenant applications must manually implement filtering on every query.

### Solution

Automatic tenant isolation via row-level filtering (`tenant_id` column) or PostgreSQL schema separation.

### Features

| Feature                          | Description                                            |
| -------------------------------- | ------------------------------------------------------ |
| **Tenant Context Middleware**    | Extracts tenant from JWT claims, headers, or subdomain |
| **Automatic QuerySet Filtering** | All queries are scoped to the current tenant           |
| **TenantMixin**                  | Model mixin that adds `tenant` FK and manager          |
| **GraphQLMeta Integration**      | `tenant_field` option for per-model configuration      |
| **Cross-Tenant Queries**         | Superuser escape hatch for admin operations            |

### Example Usage

```python
from rail_django.extensions.multitenancy import TenantMixin

class Project(TenantMixin, models.Model):
    """
    Project model with automatic tenant isolation.

    Attributes:
        name: Project name.
        organization: Auto-injected tenant reference.
    """
    name = models.CharField(max_length=100)

    class GraphQLMeta:
        tenant_field = "organization"  # Auto-filter by this field
```

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "multitenancy_settings": {
        "enabled": True,
        "isolation_mode": "row",  # "row" or "schema"
        "tenant_header": "X-Tenant-ID",
        "tenant_claim": "tenant_id",  # JWT claim
        "default_tenant_field": "organization",
        "allow_cross_tenant_superuser": True,
    }
}
```

---

## 2. Background Task Orchestration

**Module:** `rail_django.extensions.tasks`  
**Priority:** Essential for long-running operations

### Problem

Long-running operations (PDF generation, bulk exports, email campaigns) block GraphQL requests. No unified way to track async job progress.

### Solution

Celery/Dramatiq integration with built-in task tracking model and GraphQL subscriptions for real-time updates.

### Features

| Feature                      | Description                                  |
| ---------------------------- | -------------------------------------------- |
| **@task_mutation Decorator** | Wraps a mutation to run asynchronously       |
| **TaskExecution Model**      | Tracks status, progress, result, and errors  |
| **Task Subscriptions**       | Real-time `taskUpdated` subscription events  |
| **REST Endpoint**            | `/api/v1/tasks/{id}/` for polling fallback   |
| **Retry & Dead Letter**      | Configurable retry policies with DLQ         |
| **Result Storage**           | Store results in DB or external storage (S3) |

### Example Usage

```python
from rail_django.extensions.tasks import task_mutation

@task_mutation(name="generate_report", track_progress=True)
def resolve_generate_report(root, info, dataset_id: str):
    """
    Generate a PDF report asynchronously.

    Args:
        dataset_id: The dataset to generate the report from.

    Returns:
        TaskExecution instance with task_id.
    """
    # This runs in a Celery worker
    from .services import ReportService
    return ReportService.generate(dataset_id, progress_callback=info.context.task.update_progress)
```

### GraphQL API

```graphql
mutation {
  generateReport(datasetId: "123") {
    taskId
    status # PENDING
  }
}

subscription {
  taskUpdated(taskId: "abc-123") {
    status # PENDING -> RUNNING -> SUCCESS
    progress # 0 -> 50 -> 100
    resultUrl
    error
  }
}

query {
  task(id: "abc-123") {
    id
    status
    progress
    result
    createdAt
    completedAt
  }
}
```

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "task_settings": {
        "enabled": True,
        "backend": "celery",  # "celery", "dramatiq", or "django_q"
        "default_queue": "default",
        "result_ttl_seconds": 86400,
        "max_retries": 3,
        "retry_backoff": True,
        "track_in_database": True,
        "emit_subscriptions": True,
    }
}
```

---

## 3. Query Complexity Analysis

**Module:** `rail_django.extensions.complexity`  
**Priority:** Security and Performance

### Problem

Rate limiting alone doesn't protect against expensive queries. A single deeply nested query can overwhelm the server.

### Solution

Static query cost analysis with configurable limits per field, list multipliers, and depth restrictions.

### Features

| Feature                        | Description                                        |
| ------------------------------ | -------------------------------------------------- |
| **Automatic Cost Calculation** | Computes cost based on fields and nesting          |
| **Field Cost Override**        | `GraphQLMeta.field_costs` for custom weights       |
| **List Multiplier**            | Multiplies cost for list fields (pagination-aware) |
| **Depth Limiting**             | Maximum nesting depth enforcement                  |
| **Cost Header**                | Returns `X-GraphQL-Cost` header for debugging      |
| **Per-Role Limits**            | Different limits for different user roles          |

### Example Usage

```python
class Order(models.Model):
    """
    Order model with field cost annotations.
    """
    items = models.ManyToManyField("OrderItem")

    class GraphQLMeta:
        field_costs = {
            "items": 5,           # Each item fetch costs 5
            "total_amount": 2,    # Computed field
        }
        max_complexity = 500      # Per-query limit for this model
```

### GraphQL Response

```json
{
  "data": { ... },
  "extensions": {
    "complexity": {
      "cost": 142,
      "limit": 1000,
      "depth": 4,
      "maxDepth": 10
    }
  }
}
```

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "complexity_settings": {
        "enabled": True,
        "max_query_complexity": 1000,
        "max_query_depth": 10,
        "default_field_cost": 1,
        "default_list_cost": 10,
        "list_multiplier_field": "first",  # Use pagination arg
        "list_multiplier_default": 10,
        "introspection_cost": 100,
        "include_cost_header": True,
        "role_limits": {
            "admin": 5000,
            "premium": 2000,
            "default": 1000,
        },
    }
}
```

---

## 4. Soft Delete & Temporal Queries

**Module:** `rail_django.extensions.temporal`  
**Priority:** Data Governance and Compliance

### Problem

No built-in soft delete support. No way to query historical data or audit "as of" snapshots.

### Solution

Soft delete mixin with automatic filtering, plus temporal query support for point-in-time data access.

### Features

| Feature                     | Description                                   |
| --------------------------- | --------------------------------------------- |
| **SoftDeleteMixin**         | Adds `deleted_at` field with manager override |
| **Auto-Exclude Deleted**    | Queries exclude deleted records by default    |
| **includeDeleted Argument** | Opt-in to see soft-deleted records            |
| **restore Mutation**        | Undo soft deletes                             |
| **asOf Argument**           | Query data as it existed at a timestamp       |
| **History Integration**     | Optional `django-simple-history` support      |
| **Retention Policies**      | Auto-purge deleted records after N days       |

### Example Usage

```python
from rail_django.extensions.temporal import SoftDeleteMixin, TemporalMixin

class Document(SoftDeleteMixin, TemporalMixin, models.Model):
    """
    Document model with soft delete and history tracking.

    Attributes:
        title: Document title.
        content: Document body.
        deleted_at: Soft delete timestamp (null if active).
    """
    title = models.CharField(max_length=200)
    content = models.TextField()

    class GraphQLMeta:
        enable_restore = True
        enable_temporal_queries = True
        soft_delete_cascade = ["attachments"]  # Cascade soft delete
```

### GraphQL API

```graphql
# Normal query (excludes deleted)
query {
  documents {
    id
    title
  }
}

# Include soft-deleted records
query {
  documents(includeDeleted: true) {
    id
    title
    deletedAt
  }
}

# Query historical snapshot
query {
  documents(asOf: "2026-01-01T00:00:00Z") {
    id
    title
    # Returns data as it was on Jan 1st
  }
}

# Restore a soft-deleted document
mutation {
  restoreDocument(id: "123") {
    success
    document {
      id
      deletedAt # null
    }
  }
}
```

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "temporal_settings": {
        "enabled": True,
        "soft_delete_field": "deleted_at",
        "enable_include_deleted": True,
        "enable_temporal_queries": True,
        "history_backend": "django_simple_history",  # or "custom"
        "retention_days": 90,
        "retention_run_interval": 86400,
    }
}
```

---

## 5. GeoSpatial Extension

**Module:** `rail_django.extensions.gis`  
**Priority:** Critical for logistics, fleet management, location-based apps

### Problem

No PostGIS integration. No way to filter by distance, region, or spatial relationships.

### Solution

GeoJSON scalar types and spatial filter lookups integrated with `AdvancedFilterGenerator`.

### Features

| Feature                   | Description                                                   |
| ------------------------- | ------------------------------------------------------------- |
| **GeoJSON Scalars**       | `Point`, `Polygon`, `LineString`, `Geometry`                  |
| **Spatial Lookups**       | `distance_lte`, `dwithin`, `intersects`, `within`, `contains` |
| **Distance Ordering**     | `order_by: { distance_from: { point: ..., asc: true } }`      |
| **Bounding Box Filter**   | `bbox` argument for map viewport queries                      |
| **GeoDjango Integration** | Seamless wrapper around `django.contrib.gis`                  |
| **PostGIS Functions**     | Expose `ST_Distance`, `ST_Area`, etc. as computed fields      |

### Example Usage

```python
from django.contrib.gis.db import models as gis_models

class Asset(models.Model):
    """
    Asset model with geographic location.

    Attributes:
        designation: Asset identifier.
        location: GPS coordinates (Point).
        coverage_area: Service coverage polygon.
    """
    designation = models.CharField(max_length=100)
    location = gis_models.PointField(geography=True, null=True)
    coverage_area = gis_models.PolygonField(geography=True, null=True)

    class GraphQLMeta:
        gis_fields = ["location", "coverage_area"]
        enable_distance_ordering = True
```

### GraphQL API

```graphql
# Find assets within 50km of a point
query {
  assets(
    filter: {
      location__distance_lte: { point: { lat: 36.7538, lng: 3.0588 }, km: 50 }
    }
  ) {
    id
    designation
    location # { "type": "Point", "coordinates": [3.0588, 36.7538] }
  }
}

# Find assets within a polygon
query {
  assets(
    filter: {
      location__within: {
        polygon: {
          coordinates: [
            [[2.9, 36.7], [3.1, 36.7], [3.1, 36.8], [2.9, 36.8], [2.9, 36.7]]
          ]
        }
      }
    }
  ) {
    id
    designation
  }
}

# Order by distance from a point
query {
  assets(
    orderBy: {
      distanceFrom: { point: { lat: 36.75, lng: 3.05 }, direction: ASC }
    }
    first: 10
  ) {
    id
    designation
    distance # Computed field: distance in meters
  }
}

# Bounding box query (for map viewports)
query {
  assets(bbox: { minLat: 36.7, minLng: 3.0, maxLat: 36.8, maxLng: 3.1 }) {
    id
    location
  }
}
```

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "gis_settings": {
        "enabled": True,
        "default_srid": 4326,
        "distance_unit": "km",  # "m", "km", "mi"
        "enable_distance_field": True,
        "enable_area_field": True,
        "enable_bbox_filter": True,
        "geography_models": ["assets.Asset", "fleet.Vehicle"],
    }
}
```

### Dependencies

```txt
# requirements/gis.txt
django.contrib.gis
psycopg2-binary  # or psycopg[binary]
# PostgreSQL must have PostGIS extension enabled
```

---

## Summary Table

| #   | Feature              | Complexity | Impact      | Dependencies                       |
| --- | -------------------- | ---------- | ----------- | ---------------------------------- |
| 1   | Multi-Tenancy        | 🟡 Medium  | 🔴 Critical | -                                  |
| 2   | Task Orchestration   | 🟡 Medium  | 🔴 High     | `celery` or `dramatiq`             |
| 3   | Query Complexity     | 🟢 Low     | 🟡 High     | -                                  |
| 4   | Soft Delete/Temporal | 🟡 Medium  | 🟡 Medium   | `django-simple-history` (optional) |
| 5   | GeoSpatial           | 🔴 High    | 🟡 Medium   | `django.contrib.gis`, PostGIS      |

---

## Recommended Implementation Order

1. **Query Complexity** - Low effort, immediate security benefit
2. **Multi-Tenancy** - Foundation for SaaS architecture
3. **Task Orchestration** - Enables async operations across the framework
4. **Soft Delete/Temporal** - Data governance and compliance
5. **GeoSpatial** - Domain-specific, implement when needed

---

## Related Documentation

- [Extensions Index](extensions/index.md)
- [Security Guide](reference/security.md)
- [Configuration Reference](reference/configuration.md)
- [GraphQLMeta Reference](reference/meta.md)
