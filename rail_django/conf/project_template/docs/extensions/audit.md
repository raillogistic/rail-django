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
8. [Retention and Archiving](#retention-and-archiving)
9. [Best Practices](#best-practices)

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
  security_report(from_date: $from, to_date: $to) {
    summary {
      total_events
      login_successes
      login_failures
      permission_denials
      rate_limit_hits
    }
    by_severity {
      severity
      count
    }
    by_user {
      user_id
      username
      event_count
    }
    suspicious_ips {
      ip_address
      event_count
      last_event
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
  $event_type: String
  $app_label: String
  $user_id: ID
  $from: DateTime
  $to: DateTime
  $limit: Int
) {
  audit_events(
    event_type: $event_type
    app_label: $app_label
    user_id: $user_id
    from_date: $from
    to_date: $to
    limit: $limit
  ) {
    id
    event_type
    event_name
    user {
      id
      username
    }
    ip_address
    app_label
    model_name
    object_id
    object_repr
    changed_fields
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
