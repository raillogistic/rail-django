# Audit & Logging

## Overview

Rail Django includes a comprehensive audit system for tracking data modifications, authentication events, and security incidents. This guide covers configuration, event types, and best practices.

---

## Table of Contents

1. [Configuration](#configuration)
2. [Event Types](#event-types)
3. [AuditEvent Model](#auditevent-model)
4. [Automatic Logging](#automatic-logging)
5. [Logging API](#logging-api)
6. [Security Reports](#security-reports)
7. [GraphQL Query](#graphql-query)
8. [REST API Endpoints](#rest-api-endpoints)
9. [Retention and Archiving](#retention-and-archiving)
10. [Best Practices](#best-practices)

---

## Configuration

### Basic Configuration

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "enable_extension_mutations": True,
    },
}

RAIL_DJANGO_AUDIT = {
    # Activation
    "enabled": True,

    # Event types to track
    "track_data_events": True,
    "track_security_events": True,
    "track_system_events": True,

    # Granularity
    "track_field_changes": True,
    "track_old_values": True,
    "track_new_values": True,

    # Exclusions
    "exclude_apps": ["sessions", "contenttypes"],
    "exclude_models": ["audit.AuditEvent"],
    "exclude_fields": ["password", "token", "secret"],

    # Storage
    "database_alias": "default",
    "retention_days": 365,

    # Performance
    "async_logging": True,
    "batch_size": 100,
}
```

---

## Event Types

### Security Events

| Event                 | Description                  |
| --------------------- | ---------------------------- |
| `LOGIN_SUCCESS`       | Successful login             |
| `LOGIN_FAILURE`       | Failed login attempt         |
| `LOGOUT`              | User logout                  |
| `PASSWORD_CHANGE`     | Password change              |
| `PASSWORD_RESET`      | Password reset               |
| `MFA_SETUP`           | MFA device configured        |
| `MFA_VERIFY`          | MFA code verified            |
| `MFA_FAILURE`         | Failed MFA attempt           |
| `PERMISSION_DENIED`   | Authorization denied         |
| `RATE_LIMIT_EXCEEDED` | Rate limit exceeded          |
| `SUSPICIOUS_ACTIVITY` | Suspicious activity detected |

### Data Events

| Event          | Description            |
| -------------- | ---------------------- |
| `CREATE`       | Object creation        |
| `UPDATE`       | Object modification    |
| `DELETE`       | Object deletion        |
| `BULK_CREATE`  | Bulk creation          |
| `BULK_UPDATE`  | Bulk modification      |
| `BULK_DELETE`  | Bulk deletion          |
| `FIELD_ACCESS` | Sensitive field access |

### System Events

| Event               | Description           |
| ------------------- | --------------------- |
| `SCHEMA_REFRESH`    | Schema rebuilt        |
| `MIGRATION_APPLIED` | Migration applied     |
| `CACHE_CLEARED`     | Cache cleared         |
| `EXPORT_STARTED`    | Data export initiated |
| `EXPORT_COMPLETED`  | Export completed      |
| `WEBHOOK_SENT`      | Webhook sent          |
| `WEBHOOK_FAILED`    | Webhook failed        |

---

## AuditEvent Model

### Structure

```python
class AuditEvent(models.Model):
    """
    Audit event model.

    Attributes:
        event_type: Type of event (security, data, system).
        event_name: Specific event name.
        user: User who performed the action.
        ip_address: Client IP address.
        user_agent: Client User-Agent.
        app_label: Application concerned.
        model_name: Model concerned.
        object_id: Object ID.
        object_repr: Text representation of the object.
        old_values: Values before modification.
        new_values: Values after modification.
        changed_fields: List of modified fields.
        metadata: Additional metadata.
        severity: Severity level.
        timestamp: Event date and time.
    """
    EVENT_TYPES = [
        ("security", "Security"),
        ("data", "Data"),
        ("system", "System"),
    ]

    SEVERITY_LEVELS = [
        ("debug", "Debug"),
        ("info", "Info"),
        ("warning", "Warning"),
        ("error", "Error"),
        ("critical", "Critical"),
    ]

    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    event_name = models.CharField(max_length=50)
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(blank=True)
    app_label = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=100, blank=True)
    object_repr = models.TextField(blank=True)
    old_values = models.JSONField(null=True)
    new_values = models.JSONField(null=True)
    changed_fields = models.JSONField(default=list)
    metadata = models.JSONField(default=dict)
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["event_type", "timestamp"]),
            models.Index(fields=["user", "timestamp"]),
            models.Index(fields=["app_label", "model_name", "timestamp"]),
        ]
```

---

## Automatic Logging

### Enable for a Model

```python
from django.db import models
from rail_django.extensions.audit import AuditMixin

class SensitiveDocument(AuditMixin, models.Model):
    """
    Sensitive document with automatic auditing.
    """
    title = models.CharField(max_length=200)
    content = models.TextField()
    classification = models.CharField(max_length=20)

    class AuditMeta:
        # Tracked events
        track_create = True
        track_update = True
        track_delete = True

        # Fields to include/exclude
        include_fields = None  # All
        exclude_fields = ["content"]  # Don't log content

        # Sensitive field access logging
        sensitive_fields = ["classification"]
```

### Automatic Tracking via Signal

```python
# All model modifications are tracked
RAIL_DJANGO_AUDIT = {
    "auto_track_models": True,
    "exclude_models": ["sessions.Session"],
}
```

---

## Logging API

### Manual Logging

```python
from rail_django.extensions.audit import audit_log

# Security event
audit_log.security(
    event_name="SUSPICIOUS_ACTIVITY",
    user=request.user,
    request=request,
    metadata={
        "reason": "Multiple failed login attempts",
        "attempt_count": 5,
    },
    severity="warning",
)

# Data event
audit_log.data(
    event_name="EXPORT_STARTED",
    user=request.user,
    request=request,
    app_label="store",
    model_name="Product",
    metadata={
        "format": "xlsx",
        "record_count": 1500,
    },
)

# System event
audit_log.system(
    event_name="CACHE_CLEARED",
    metadata={
        "cache_key": "products_*",
        "reason": "Manual refresh",
    },
)
```

### Logging Decorator

```python
from rail_django.extensions.audit import audit_action

@audit_action(event_name="CUSTOM_ACTION", event_type="data")
def my_sensitive_function(request, **kwargs):
    """
    Automatically logged function.
    """
    # ... logic
    return result
```

---

## Security Reports

### Execute via GraphQL

```graphql
query SecurityReport($from: DateTime!, $to: DateTime!) {
  securityReport(fromDate: $from, toDate: $to) {
    summary {
      totalEvents
      loginSuccesses
      loginFailures
      permissionDenials
      rateLimitHits
    }
    bySeverity {
      severity
      count
    }
    byUser {
      userId
      username
      eventCount
    }
    suspiciousIps {
      ipAddress
      eventCount
      lastEvent
    }
  }
}
```

### Generate Scheduled Report

```python
from rail_django.extensions.audit import generate_security_report

# Daily report
report = generate_security_report(
    from_date=timezone.now() - timedelta(days=1),
    to_date=timezone.now(),
    format="pdf",
)

# Send by email
send_report_email(
    to=["security@example.com"],
    subject="Daily Security Report",
    attachment=report,
)
```

---

## GraphQL Query

### Query Audit Events

```graphql
query AuditEvents(
  $eventType: String
  $appLabel: String
  $userId: ID
  $from: DateTime
  $to: DateTime
  $limit: Int
) {
  auditEvents(
    eventType: $eventType
    appLabel: $appLabel
    userId: $userId
    fromDate: $from
    toDate: $to
    limit: $limit
  ) {
    id
    eventType
    eventName
    user {
      id
      username
    }
    ipAddress
    appLabel
    modelName
    objectId
    objectRepr
    changedFields
    severity
    timestamp
  }
}
```

### Query for a Specific Object

```graphql
query ObjectHistory(
  $app_label: String!
  $model_name: String!
  $object_id: ID!
) {
  object_audit_history(
    app_label: $app_label
    model_name: $model_name
    object_id: $object_id
  ) {
    id
    event_name
    user {
      username
    }
    old_values
    new_values
    changed_fields
    timestamp
  }
}
```

---

## REST API Endpoints

Rail Django provides protected REST API endpoints for accessing audit logs programmatically. These endpoints require authentication and admin/staff privileges or the `rail_django.view_auditeventmodel` permission.

### URL Configuration

```python
# root/urls.py
from django.urls import path, include
from rail_django.views.audit_views import get_audit_urls

urlpatterns = [
    # ... other URLs
    path("api/v1/", include(get_audit_urls())),
]
```

This registers the following endpoints:

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/audit/` | List audit events with filtering |
| `GET /api/v1/audit/stats/` | Audit statistics and aggregations |
| `GET /api/v1/audit/security-report/` | Security threat analysis |
| `GET /api/v1/audit/event/<id>/` | Single audit event detail |
| `GET /api/v1/audit/meta/` | Available event types and severities |

### Authentication

All endpoints require:
- **Authentication**: User must be logged in (returns 401 if not)
- **Authorization**: User must be superuser, staff, or have `rail_django.view_auditeventmodel` permission (returns 403 if not)

### List Audit Events

**GET /api/v1/audit/**

Query audit events with rich filtering capabilities.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `event_type` | string | Filter by single event type |
| `event_types` | list | Filter by multiple event types |
| `severity` | string | Filter by severity (low, medium, high, critical) |
| `severities` | list | Filter by multiple severities |
| `user_id` | integer | Filter by user ID |
| `username` | string | Filter by username (partial match) |
| `client_ip` | string | Filter by client IP address |
| `success` | boolean | Filter by success status (true/false) |
| `date_from` | ISO datetime | Filter events from this date |
| `date_to` | ISO datetime | Filter events until this date |
| `hours` | integer | Filter events from last N hours |
| `request_path` | string | Filter by request path (partial match) |
| `session_id` | string | Filter by session ID |
| `search` | string | Full-text search in additional_data, error_message, request_path |
| `page` | integer | Page number (default: 1) |
| `page_size` | integer | Items per page (default: 50, max: 500) |
| `order_by` | string | Sort field: timestamp, -timestamp, event_type, severity, user_id |

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/v1/audit/?event_type=login_failure&hours=24&page_size=10" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

**Response:**

```json
{
  "events": [
    {
      "id": 1234,
      "event_type": "login_failure",
      "severity": "medium",
      "user_id": null,
      "username": "unknown_user",
      "client_ip": "192.168.1.100",
      "user_agent": "Mozilla/5.0...",
      "timestamp": "2024-01-15T10:30:00+00:00",
      "request_path": "/graphql/",
      "request_method": "POST",
      "additional_data": {"reason": "invalid_password"},
      "session_id": null,
      "success": false,
      "error_message": "Invalid credentials"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 10,
    "total_count": 45,
    "total_pages": 5,
    "has_next": true,
    "has_previous": false
  },
  "timestamp": "2024-01-15T12:00:00+00:00"
}
```

### Audit Statistics

**GET /api/v1/audit/stats/**

Get aggregated statistics for the specified time period.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `hours` | integer | Time period in hours (default: 24) |

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/v1/audit/stats/?hours=24" \
  -H "Authorization: Bearer <token>"
```

**Response:**

```json
{
  "period_hours": 24,
  "total_events": 1250,
  "by_event_type": {
    "login_success": 500,
    "login_failure": 45,
    "create": 300,
    "update": 350,
    "delete": 55
  },
  "by_severity": {
    "low": 800,
    "medium": 400,
    "high": 45,
    "critical": 5
  },
  "by_success": {
    "successful": 1150,
    "failed": 100
  },
  "top_failed_ips": [
    {"client_ip": "192.168.1.100", "count": 15},
    {"client_ip": "10.0.0.50", "count": 8}
  ],
  "top_users": [
    {"username": "admin", "user_id": 1, "count": 200},
    {"username": "john_doe", "user_id": 5, "count": 150}
  ],
  "top_event_types": [
    {"event_type": "login_success", "count": 500},
    {"event_type": "update", "count": 350}
  ],
  "high_severity_count": 50,
  "timestamp": "2024-01-15T12:00:00+00:00"
}
```

### Security Report

**GET /api/v1/audit/security-report/**

Generate a comprehensive security report with threat analysis.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `hours` | integer | Time period in hours (default: 24) |

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/v1/audit/security-report/?hours=24" \
  -H "Authorization: Bearer <token>"
```

**Response:**

```json
{
  "period_hours": 24,
  "brute_force_suspects": [
    {"client_ip": "192.168.1.100", "attempts": 25},
    {"client_ip": "10.0.0.50", "attempts": 12}
  ],
  "suspicious_events": [
    {
      "client_ip": "192.168.1.100",
      "username": null,
      "timestamp": "2024-01-15T10:30:00+00:00",
      "additional_data": {"pattern": "credential_stuffing"}
    }
  ],
  "rate_limited_ips": [
    {"client_ip": "192.168.1.100", "count": 50}
  ],
  "high_severity_timeline": [
    {
      "event_type": "suspicious_activity",
      "severity": "high",
      "client_ip": "192.168.1.100",
      "username": null,
      "timestamp": "2024-01-15T10:30:00+00:00",
      "success": false
    }
  ],
  "generated_at": "2024-01-15T12:00:00+00:00"
}
```

### Single Event Detail

**GET /api/v1/audit/event/<id>/**

Retrieve full details of a single audit event.

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/v1/audit/event/1234/" \
  -H "Authorization: Bearer <token>"
```

**Response:**

```json
{
  "event": {
    "id": 1234,
    "event_type": "login_failure",
    "severity": "medium",
    "user_id": null,
    "username": "unknown_user",
    "client_ip": "192.168.1.100",
    "user_agent": "Mozilla/5.0...",
    "timestamp": "2024-01-15T10:30:00+00:00",
    "request_path": "/graphql/",
    "request_method": "POST",
    "additional_data": {"reason": "invalid_password"},
    "session_id": null,
    "success": false,
    "error_message": "Invalid credentials"
  },
  "timestamp": "2024-01-15T12:00:00+00:00"
}
```

### Event Types Metadata

**GET /api/v1/audit/meta/**

List all available event types and severity levels.

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/v1/audit/meta/" \
  -H "Authorization: Bearer <token>"
```

**Response:**

```json
{
  "event_types": [
    "login_success",
    "login_failure",
    "logout",
    "password_change",
    "mfa_setup",
    "mfa_verify",
    "permission_denied",
    "rate_limited",
    "suspicious_activity",
    "create",
    "update",
    "delete"
  ],
  "severities": ["low", "medium", "high", "critical"],
  "timestamp": "2024-01-15T12:00:00+00:00"
}
```

### Error Responses

All endpoints return consistent error responses:

**401 Unauthorized:**
```json
{
  "error": "Authentication required",
  "code": "UNAUTHENTICATED"
}
```

**403 Forbidden:**
```json
{
  "error": "Admin privileges required to access audit logs",
  "code": "FORBIDDEN"
}
```

**404 Not Found (event detail only):**
```json
{
  "error": "Audit event not found",
  "code": "NOT_FOUND"
}
```

**400 Bad Request:**
```json
{
  "error": "Invalid parameter: ...",
  "code": "INVALID_PARAMETER"
}
```

**500 Internal Server Error:**
```json
{
  "error": "Internal server error",
  "code": "INTERNAL_ERROR"
}
```

---

## Retention and Archiving

### Automatic Cleanup

```python
RAIL_DJANGO_AUDIT = {
    "retention_days": 365,  # Keep 1 year
    "archive_before_delete": True,
    "archive_path": "/backups/audit/",
}
```

### Management Command

```bash
# Clean old events
python manage.py cleanup_audit_events --days 365

# Archive before cleaning
python manage.py archive_audit_events --days 365 --output /backups/

# Force without confirmation
python manage.py cleanup_audit_events --days 365 --force
```

### Archiving Task

```python
# Use with Celery
from celery import shared_task

@shared_task
def archive_old_audit_events():
    from rail_django.extensions.audit import archive_events

    archived_count = archive_events(
        older_than_days=365,
        output_path="/backups/audit/",
        delete_after_archive=True,
    )
    return f"Archived {archived_count} events"
```

---

## Best Practices

### 1. Exclude Sensitive Fields

```python
RAIL_DJANGO_AUDIT = {
    "exclude_fields": [
        "password",
        "token",
        "secret",
        "api_key",
        "credit_card",
    ],
}
```

### 2. Configure Severity

```python
# Model-level custom severity
class FinancialTransaction(AuditMixin, models.Model):
    class AuditMeta:
        default_severity = "warning"  # All events are important
```

### 3. Use Metadata

```python
audit_log.data(
    event_name="PAYMENT_PROCESSED",
    metadata={
        "amount": 1500.00,
        "currency": "EUR",
        "payment_method": "card",
        "transaction_id": "txn_123",
    },
)
```

### 4. Monitor Critical Events

```python
# Alert on critical events
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=AuditEvent)
def notify_critical_events(sender, instance, **kwargs):
    if instance.severity == "critical":
        send_security_alert(instance)
```

### 5. Regular Reporting

```python
# Scheduled task for weekly report
@shared_task
def weekly_security_report():
    report = generate_security_report(
        from_date=timezone.now() - timedelta(days=7),
        to_date=timezone.now(),
    )
    send_report_email(report)
```

---

## See Also

- [Authentication](../security/authentication.md) - Authentication events
- [Permissions](../security/permissions.md) - Permission auditing
- [Observability](./observability.md) - Sentry and metrics
