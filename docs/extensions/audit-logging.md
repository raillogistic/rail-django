# Audit & Logging

## Overview

Rail Django includes a comprehensive audit system for tracking data modifications, authentication events, and security incidents. The system records mutations and sensitive queries to the database or an external store.

---

## Table of Contents

1. [Configuration](#configuration)
2. [How It Works](#how-it-works)
3. [Event Types](#event-types)
4. [AuditEvent Model](#auditevent-model)
5. [Automatic Logging](#automatic-logging)
6. [Logging API](#logging-api)
7. [Security Reports](#security-reports)
8. [GraphQL Queries](#graphql-queries)
9. [REST API Endpoints](#rest-api-endpoints)
10. [Retention and Archiving](#retention-and-archiving)
11. [Best Practices](#best-practices)

---

## Configuration

Enable audit logging in your `settings.py`:

```python
# settings.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "enable_extension_mutations": True,
    },
    "audit_settings": {
        "enabled": True,
        "store_in_database": True, # Set to False if using external logger
        "exclude_mutations": ["login", "refreshToken"],
        "mask_fields": ["password", "token", "credit_card"],
    }
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

## How It Works

1.  **Interception**: Middleware intercepts every GraphQL request.
2.  **Analysis**: It checks if the operation is a mutation or a flagged query.
3.  **Recording**: It saves an `AuditLog` (or `AuditEvent`) entry.

### Tracking Admin and ORM Changes

GraphQL audit logging does not cover Django admin or direct ORM writes. Rail Django provides a signal handler that emits security events for model creates, updates, deletes, and many-to-many changes.

The signal handler:
- Emits `DATA_*` events for `post_save`, `post_delete`, and `m2m_changed`.
- Limits auditing to project apps by default.
- Can be scoped using `AUDIT_SIGNAL_APP_LABELS` in settings.

```python
# settings.py
AUDIT_SIGNAL_APP_LABELS = ["root", "store"]
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
from rail_django.extensions.audit.models import AuditEvent

# The model tracks:
# - event_type: Type of event (security, data, system)
# - event_name: Specific event name
# - user: User who performed the action
# - ip_address: Client IP address
# - user_agent: Client User-Agent
# - app_label / model_name / object_id
# - old_values / new_values / changed_fields
# - metadata / severity / timestamp
```

---

## Automatic Logging

### Enable for a Model

```python
from django.db import models
from rail_django.extensions.audit import AuditMixin

class SensitiveDocument(AuditMixin, models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()

    class AuditMeta:
        track_create = True
        track_update = True
        track_delete = True
        exclude_fields = ["content"]
        sensitive_fields = ["classification"]
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
    metadata={"reason": "Multiple failed login attempts"},
    severity="warning",
)
```

### Logging Decorator

```python
from rail_django.extensions.audit import audit_action

@audit_action(event_name="CUSTOM_ACTION", event_type="data")
def my_sensitive_function(request, **kwargs):
    # ... logic
    return result
```

---

## Security Reports

Reports can be generated via GraphQL or programmatically:

```python
from rail_django.extensions.audit import generate_security_report

report = generate_security_report(
    from_date=timezone.now() - timedelta(days=1),
    to_date=timezone.now(),
    format="pdf",
)
```

---

## GraphQL Queries

### Query Audit Events

```graphql
query AuditEvents($limit: Int) {
  auditEvents(limit: $limit) {
    id
    eventType
    eventName
    user { username }
    ipAddress
    timestamp
  }
}
```

### Query for a Specific Object

```graphql
query ObjectHistory($app_label: String!, $model_name: String!, $object_id: ID!) {
  object_audit_history(
    app_label: $app_label
    model_name: $model_name
    object_id: $object_id
  ) {
    id
    event_name
    old_values
    new_values
    timestamp
  }
}
```

---

## REST API Endpoints

Rail Django provides protected REST API endpoints at `/api/v1/audit/`.

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/audit/` | List audit events with filtering |
| `GET /api/v1/audit/stats/` | Audit statistics and aggregations |
| `GET /api/v1/audit/security-report/` | Security threat analysis |
| `GET /api/v1/audit/event/<id>/` | Single audit event detail |

---

## Retention and Archiving

### Automatic Cleanup

```python
RAIL_DJANGO_AUDIT = {
    "retention_days": 365,
    "archive_before_delete": True,
    "archive_path": "/backups/audit/",
}
```

### Management Command

```bash
python manage.py cleanup_audit_events --days 365
```

---

## Best Practices

1. **Exclude Sensitive Fields**: Always mask or exclude passwords, tokens, and secrets.
2. **Use Async Logging**: For high-traffic applications, enable `async_logging` to prevent audit writes from blocking requests.
3. **Monitor Critical Events**: Set up alerts for `critical` severity events.
4. **Regular Reporting**: Schedule weekly or daily security reports.

---

## Custom Logger

If you want to send logs to ELK, Splunk, or Datadog instead of the DB, listen to the `audit_log_record` signal:

```python
from django.dispatch import receiver
from rail_django.extensions.audit.signals import audit_log_record

@receiver(audit_log_record)
def send_to_external_store(sender, log_entry, **kwargs):
    external_logger.send(log_entry.to_dict())
```
