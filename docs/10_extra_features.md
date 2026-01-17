# 10 Enterprise Features Roadmap

This document outlines ten high-impact enterprise features recommended for implementation in `rail-django`. These features address common gaps in enterprise GraphQL APIs and align with industry standards (Hasura, PostGraphile, Apollo Federation).

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

Thread/Celery/Dramatiq integration with a task tracking model and GraphQL subscriptions for real-time updates.

### Features

| Feature                      | Description                                  |
| ---------------------------- | -------------------------------------------- |
| **@task_mutation Decorator** | Wraps a mutation to run asynchronously       |
| **TaskExecution Model**      | Tracks status, progress, result, and errors  |
| **Task Subscriptions**       | Real-time `task_updated` subscription events |
| **REST Endpoint**            | `/api/v1/tasks/{id}/` for polling fallback   |
| **Retry & Dead Letter**      | Configurable retry policies with DLQ         |
| **Result Storage**           | Store results in DB or external storage (S3) |

### Example Usage

```python
import graphene
from rail_django.extensions.tasks import task_mutation

@task_mutation(name="generate_report", track_progress=True)
def generate_report(root, info, dataset_id: str):
    """
    Generate a PDF report asynchronously.

    Args:
        dataset_id: The dataset to generate the report from.

    Returns:
        TaskExecution instance with task_id.
    """
    # This runs in a Celery worker
    from .services import ReportService
    return ReportService.generate(
        dataset_id, progress_callback=info.context.task.update_progress
    )


class TaskMutations(graphene.ObjectType):
    generate_report = generate_report
```

Register the task mutation class:

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "mutation_extensions": ["myapp.graphql.TaskMutations"],
    }
}
```

### GraphQL API

```graphql
mutation {
  generate_report(dataset_id: "123") {
    task_id
    status # PENDING
  }
}

subscription {
  task_updated(task_id: "abc-123") {
    status # PENDING -> RUNNING -> SUCCESS
    progress # 0 -> 50 -> 100
    result
    error
  }
}

query {
  task(id: "abc-123") {
    id
    status
    progress
    result
    created_at
    completed_at
  }
}
```

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "task_settings": {
        "enabled": True,
        "backend": "thread",  # "thread", "sync", "celery", "dramatiq", or "django_q"
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
psycopg2  # or psycopg[binary]
# PostgreSQL must have PostGIS extension enabled
```

---

## 6. Workflow & State Machine (FSM)

**Module:** `rail_django.extensions.workflow`  
**Priority:** Critical for business process automation

### Problem

No built-in support for state machines. Business entities (orders, tickets, approvals) require explicit state transitions with validation and side effects.

### Solution

Integration with `django-fsm` providing GraphQL mutations for state transitions, guards, and automatic audit logging.

### Features

| Feature                  | Description                                           |
| ------------------------ | ----------------------------------------------------- |
| **FSM Field Support**    | Auto-detect `FSMField` and expose allowed transitions |
| **Transition Mutations** | Auto-generated `transitionOrderTo{State}` mutations   |
| **Transition Guards**    | Permission checks before state changes                |
| **Side Effects**         | Hooks for actions on enter/exit states                |
| **Transition History**   | Built-in logging of all state changes                 |
| **Visual Graph**         | Export state machine as DOT/Mermaid diagram           |

### Example Usage

```python
from django.db import models
from django_fsm import FSMField, transition
from rail_django.extensions.workflow import WorkflowMixin

class Order(WorkflowMixin, models.Model):
    """
    Order model with state machine workflow.

    Attributes:
        status: Current order state.
        customer: Customer reference.
    """
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("completed", "Completed"),
    ]

    status = FSMField(default="draft", choices=STATUS_CHOICES)
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE)

    @transition(field=status, source="draft", target="submitted")
    def submit(self):
        """Submit the order for approval."""
        pass

    @transition(
        field=status,
        source="submitted",
        target="approved",
        permission="orders.can_approve"
    )
    def approve(self, approved_by):
        """Approve the order."""
        self.approved_by = approved_by
        self.approved_at = timezone.now()

    @transition(field=status, source="submitted", target="rejected")
    def reject(self, reason):
        """Reject the order with a reason."""
        self.rejection_reason = reason

    class GraphQLMeta:
        workflow_field = "status"
        expose_transitions = True
        transition_permissions = {
            "approve": ["orders.can_approve"],
            "reject": ["orders.can_approve"],
        }
```

### GraphQL API

```graphql
# Query available transitions
query {
  order(id: "123") {
    id
    status
    availableTransitions # ["submit"]
  }
}

# Execute a transition
mutation {
  transitionOrderSubmit(id: "123") {
    success
    order {
      id
      status # "submitted"
    }
    errors
  }
}

# Transition with parameters
mutation {
  transitionOrderApprove(id: "123", approvedBy: "user_456") {
    success
    order {
      status # "approved"
      approvedBy {
        id
        name
      }
    }
  }
}

# Query transition history
query {
  order(id: "123") {
    transitionHistory {
      fromState
      toState
      transitionName
      performedBy {
        username
      }
      performedAt
      metadata
    }
  }
}
```

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "workflow_settings": {
        "enabled": True,
        "auto_detect_fsm_fields": True,
        "expose_available_transitions": True,
        "log_transitions": True,
        "transition_history_model": "rail_django.TransitionLog",
        "emit_transition_events": True,  # Webhooks/subscriptions
    }
}
```

### Dependencies

```txt
django-fsm>=2.8.0
```

---

## 7. API Versioning

**Module:** `rail_django.extensions.versioning`  
**Priority:** Essential for API stability and evolution

### Problem

No formal strategy for evolving the GraphQL API without breaking existing clients. Deprecations are manual and error-prone.

### Solution

Schema versioning with automatic deprecation management, breaking change detection, and client version negotiation.

### Features

| Feature                       | Description                                       |
| ----------------------------- | ------------------------------------------------- |
| **Version Header**            | `X-API-Version: 2024-01-01` for client requests   |
| **Schema Snapshots**          | Immutable schema versions stored in registry      |
| **Deprecation Tracking**      | `@deprecated` with sunset dates and replacements  |
| **Breaking Change Detection** | CI/CD integration to block breaking changes       |
| **Version Negotiation**       | Automatic field filtering based on client version |
| **Migration Guides**          | Auto-generated upgrade documentation              |

### Example Usage

```python
from rail_django.extensions.versioning import deprecated, since_version

class Product(models.Model):
    """
    Product model with versioned fields.
    """
    name = models.CharField(max_length=100)
    sku = models.CharField(max_length=50)

    # Legacy field - deprecated in favor of sku
    code = models.CharField(max_length=50)

    # New field added in v2
    metadata = models.JSONField(default=dict)

    class GraphQLMeta:
        field_versions = {
            "code": deprecated(
                since="2025-06-01",
                sunset="2026-01-01",
                replacement="sku",
                reason="Renamed for consistency"
            ),
            "metadata": since_version("2025-06-01"),
        }
```

### GraphQL Schema

```graphql
type Product {
  id: ID!
  name: String!
  sku: String!

  # Deprecated field (visible to older clients)
  code: String @deprecated(reason: "Use 'sku' instead. Sunset: 2026-01-01")

  # New field (hidden from clients before 2025-06-01)
  metadata: JSONString
}
```

### GraphQL API

```graphql
# Query API versions
query {
  apiVersions {
    current
    supported
    deprecated {
      version
      sunsetDate
    }
  }
}

# Query schema changelog
query {
  schemaChangelog(fromVersion: "2025-01-01", toVersion: "2025-06-01") {
    breakingChanges {
      type
      path
      description
    }
    deprecations {
      field
      reason
      replacement
      sunsetDate
    }
    additions {
      type
      path
    }
  }
}
```

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "versioning_settings": {
        "enabled": True,
        "current_version": "2025-06-01",
        "supported_versions": ["2024-01-01", "2025-01-01", "2025-06-01"],
        "version_header": "X-API-Version",
        "default_version": "latest",  # or specific date
        "hide_deprecated_after_sunset": True,
        "breaking_change_policy": "warn",  # "warn", "error", "allow"
        "store_snapshots": True,
    }
}
```

---

## 8. Data Federation & Remote Schema Stitching

**Module:** `rail_django.extensions.federation`  
**Priority:** High for microservices architecture

### Problem

No way to combine multiple GraphQL services into a unified schema. Microservices require manual API composition.

### Solution

Apollo Federation-compatible schema stitching with remote schema introspection and entity resolution.

### Features

| Feature                       | Description                                   |
| ----------------------------- | --------------------------------------------- |
| **Remote Schema Integration** | Stitch external GraphQL services              |
| **Entity Resolution**         | `@key` directive for cross-service references |
| **Type Extensions**           | Extend remote types with local fields         |
| **Query Batching**            | Optimize federated queries with DataLoader    |
| **Circuit Breaker**           | Graceful degradation when remotes fail        |
| **Schema Validation**         | Validate stitched schema compatibility        |

### Example Usage

```python
# settings.py
RAIL_DJANGO_GRAPHQL = {
    "federation_settings": {
        "enabled": True,
        "remote_schemas": [
            {
                "name": "payments",
                "url": "https://payments.internal/graphql",
                "headers": {"Authorization": "Bearer ${PAYMENTS_API_KEY}"},
                "timeout": 5.0,
                "retry_count": 2,
            },
            {
                "name": "inventory",
                "url": "https://inventory.internal/graphql",
                "introspection_interval": 3600,  # Re-fetch schema hourly
            },
        ],
    }
}
```

```python
# models.py
from rail_django.extensions.federation import federated_type, external_field

@federated_type(keys=["id"])
class Order(models.Model):
    """
    Order model that references external Payment entity.
    """
    payment_id = models.CharField(max_length=100)

    class GraphQLMeta:
        # Extend with field from remote schema
        extend_with = {
            "payment": external_field(
                schema="payments",
                type="Payment",
                resolve_by="payment_id",
            ),
        }
```

### GraphQL API

```graphql
# Unified query across services
query {
  order(id: "123") {
    id
    items {
      productId
      quantity
      # From inventory service
      product {
        name
        stockLevel
        warehouse {
          location
        }
      }
    }
    # From payments service
    payment {
      status
      amount
      processedAt
    }
  }
}

# Federation health check
query {
  federationStatus {
    remotes {
      name
      healthy
      lastIntrospection
      latencyMs
    }
  }
}
```

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "federation_settings": {
        "enabled": True,
        "mode": "gateway",  # "gateway" or "subgraph"
        "enable_entities": True,
        "circuit_breaker": {
            "failure_threshold": 5,
            "recovery_timeout": 30,
        },
        "query_batching": True,
        "batch_max_size": 50,
        "introspection_cache_ttl": 3600,
    }
}
```

### Dependencies

```txt
httpx>=0.25.0
graphql-core>=3.2.0
```

---

## 9. Internationalization (i18n) Extension

**Module:** `rail_django.extensions.i18n`  
**Priority:** Essential for global applications

### Problem

No GraphQL-native translation layer. Internationalized content requires custom resolver logic for each field.

### Solution

Automatic translation field resolution with `django-modeltranslation` integration and dynamic locale switching.

### Features

| Feature                          | Description                                  |
| -------------------------------- | -------------------------------------------- |
| **Translated Fields**            | Auto-detect `django-modeltranslation` fields |
| **Locale Argument**              | `locale: "fr"` argument on queries           |
| **Accept-Language Header**       | Automatic locale from HTTP headers           |
| **Fallback Chain**               | `fr-CA -> fr -> en` fallback resolution      |
| **Translation Mutations**        | CRUD for translated content                  |
| **Missing Translation Tracking** | Log/alert on missing translations            |

### Example Usage

```python
# models.py
from django.db import models
from modeltranslation.translator import register, TranslationOptions

class Article(models.Model):
    """
    Article model with translatable fields.

    Attributes:
        title: Article title (translatable).
        content: Article body (translatable).
        slug: URL slug.
    """
    title = models.CharField(max_length=200)
    content = models.TextField()
    slug = models.SlugField(unique=True)

    class GraphQLMeta:
        translatable_fields = ["title", "content"]
        translation_fallback = True


# translation.py
@register(Article)
class ArticleTranslationOptions(TranslationOptions):
    fields = ("title", "content")
```

### GraphQL API

```graphql
# Query with explicit locale
query {
  article(slug: "hello-world", locale: "fr") {
    id
    title # "Bonjour le monde"
    content # French content
    slug # "hello-world" (not translated)
  }
}

# Query all translations
query {
  article(slug: "hello-world") {
    id
    title # Default locale
    translations {
      locale
      title
      content
    }
    availableLocales # ["en", "fr", "es"]
  }
}

# Update translation
mutation {
  updateArticleTranslation(
    id: "123"
    locale: "es"
    input: { title: "Hola Mundo", content: "Contenido en español..." }
  ) {
    success
    article {
      translations {
        locale
        title
      }
    }
  }
}

# Query missing translations
query {
  missingTranslations(model: "Article", targetLocale: "de") {
    objectId
    field
    fallbackValue
  }
}
```

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "i18n_settings": {
        "enabled": True,
        "default_locale": "en",
        "supported_locales": ["en", "fr", "es", "ar"],
        "locale_header": "Accept-Language",
        "locale_argument": "locale",
        "fallback_chain": {
            "fr-CA": ["fr", "en"],
            "es-MX": ["es", "en"],
            "default": ["en"],
        },
        "expose_all_translations": True,
        "track_missing_translations": True,
        "missing_translation_log_level": "warning",
    }
}
```

### Dependencies

```txt
django-modeltranslation>=0.18.0
```

---

## 10. Notification System

**Module:** `rail_django.extensions.notifications`  
**Priority:** High for user engagement

### Problem

No unified notification system. Email, SMS, push, and in-app notifications require separate implementations.

### Solution

Multi-channel notification hub with template management, delivery tracking, and user preferences.

### Features

| Feature                    | Description                             |
| -------------------------- | --------------------------------------- |
| **Multi-Channel Delivery** | Email, SMS, Push, In-App, Slack, Teams  |
| **Template Engine**        | Django templates or Jinja2 for content  |
| **User Preferences**       | Per-user channel and frequency settings |
| **Delivery Tracking**      | Status, opens, clicks, failures         |
| **Batch Notifications**    | Digest mode for high-frequency events   |
| **GraphQL Subscriptions**  | Real-time in-app notifications          |
| **Retry & DLQ**            | Failed delivery retry with dead letter  |

### Example Usage

```python
# notifications.py
from rail_django.extensions.notifications import (
    notification,
    NotificationChannel,
    NotificationPriority,
)

@notification(
    name="order_shipped",
    channels=[NotificationChannel.EMAIL, NotificationChannel.PUSH, NotificationChannel.IN_APP],
    priority=NotificationPriority.HIGH,
)
class OrderShippedNotification:
    """
    Notification sent when an order is shipped.
    """
    template = "notifications/order_shipped.html"
    subject = "Your order #{{ order.id }} has shipped!"

    def get_context(self, order, user):
        return {
            "order": order,
            "user": user,
            "tracking_url": order.get_tracking_url(),
        }

    def get_recipients(self, order):
        return [order.customer]


# Trigger notification
from rail_django.extensions.notifications import notify

notify("order_shipped", order=order, user=order.customer)
```

```python
# models.py
class Order(models.Model):
    """
    Order model with notification triggers.
    """
    status = models.CharField(max_length=50)
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE)

    class GraphQLMeta:
        notifications = {
            "on_status_change": {
                "shipped": "order_shipped",
                "delivered": "order_delivered",
            }
        }
```

### GraphQL API

```graphql
# Query user notifications
query {
  myNotifications(first: 20, unreadOnly: true) {
    edges {
      node {
        id
        type
        title
        message
        readAt
        createdAt
        actionUrl
        metadata
      }
    }
    unreadCount
  }
}

# Mark as read
mutation {
  markNotificationsRead(ids: ["notif_123", "notif_456"]) {
    success
    updatedCount
  }
}

# Update notification preferences
mutation {
  updateNotificationPreferences(
    input: {
      channels: {
        email: { enabled: true, digest: DAILY }
        push: { enabled: true }
        sms: { enabled: false }
      }
      subscriptions: {
        orderUpdates: true
        marketing: false
        systemAlerts: true
      }
    }
  ) {
    success
    preferences {
      channels {
        email {
          enabled
          digest
        }
      }
    }
  }
}

# Real-time subscription
subscription {
  notificationReceived {
    id
    type
    title
    message
    createdAt
  }
}
```

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "notification_settings": {
        "enabled": True,
        "channels": {
            "email": {
                "enabled": True,
                "backend": "django.core.mail.backends.smtp.EmailBackend",
                "from_address": "notifications@example.com",
            },
            "push": {
                "enabled": True,
                "provider": "firebase",  # or "onesignal", "pusher"
                "credentials_path": "/secrets/firebase.json",
            },
            "sms": {
                "enabled": True,
                "provider": "twilio",
                "from_number": "+1234567890",
            },
            "in_app": {
                "enabled": True,
                "emit_subscription": True,
            },
            "slack": {
                "enabled": False,
                "webhook_url": "${SLACK_WEBHOOK_URL}",
            },
        },
        "default_channels": ["email", "in_app"],
        "digest_default_interval": "daily",  # "immediate", "hourly", "daily", "weekly"
        "retention_days": 90,
        "max_retries": 3,
        "track_opens": True,
        "track_clicks": True,
    }
}
```

### Dependencies

```txt
# Optional per channel
firebase-admin>=6.0.0  # Push notifications
twilio>=8.0.0          # SMS
slack-sdk>=3.20.0      # Slack
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
| 6   | Workflow/FSM         | 🟡 Medium  | 🔴 High     | `django-fsm`                       |
| 7   | API Versioning       | 🟡 Medium  | 🟡 High     | -                                  |
| 8   | Data Federation      | 🔴 High    | 🟡 Medium   | `httpx`                            |
| 9   | Internationalization | 🟡 Medium  | 🟡 High     | `django-modeltranslation`          |
| 10  | Notification System  | 🔴 High    | 🔴 High     | Per-channel SDKs                   |

---

## Recommended Implementation Order

### Phase 1: Security & Performance (Quick Wins)

1. **Query Complexity** - Low effort, immediate security benefit

### Phase 2: Core Architecture

2. **Multi-Tenancy** - Foundation for SaaS architecture
3. **Task Orchestration** - Enables async operations across the framework
4. **Workflow/FSM** - Business process standardization

### Phase 3: Data Management

5. **Soft Delete/Temporal** - Data governance and compliance
6. **API Versioning** - API evolution and stability

### Phase 4: User Experience

7. **Internationalization** - Global market support
8. **Notification System** - User engagement and communication

### Phase 5: Advanced Features

9. **GeoSpatial** - Domain-specific, implement when needed
10. **Data Federation** - Microservices architecture support

---

## Related Documentation

- [Extensions Index](extensions/index.md)
- [Security Guide](reference/security.md)
- [Configuration Reference](reference/configuration.md)
- [GraphQLMeta Reference](reference/meta.md)
