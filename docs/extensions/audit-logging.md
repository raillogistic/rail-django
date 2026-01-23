# Audit Logging

The Audit Logging extension records mutations and sensitive queries to the database or an external store.

## Configuration

Enable it in `settings.py`:

```python
RAIL_DJANGO_GRAPHQL = {
    "audit_settings": {
        "enabled": True,
        "store_in_database": True, # Set to False if using external logger
        "exclude_mutations": ["login", "refreshToken"],
        "mask_fields": ["password", "token", "credit_card"],
    }
}
```

## How It Works

1.  **Interception**: Middleware intercepts every GraphQL request.
2.  **Analysis**: It checks if the operation is a mutation or a flagged query.
3.  **Recording**: It saves an `AuditLog` entry.

## Tracking Admin and ORM Changes

GraphQL audit logging does not cover Django admin or direct ORM writes. The
project template ships with a small signal handler that emits security events
for model creates, updates, deletes, and many-to-many changes. This makes
admin edits show up in the audit logs without extra coding.

The signal handler:

- Emits `EventType.DATA_*` events for `post_save`, `post_delete`, and `m2m_changed`.
- Limits auditing to project apps by default (excludes Django and third-party apps).
- Can be scoped using `AUDIT_SIGNAL_APP_LABELS` in settings.

Example configuration:

```python
# settings.py
AUDIT_SIGNAL_APP_LABELS = ["root", "store"]
```

## Accessing Logs

If `store_in_database` is True, you can query logs via the `AuditLog` model.

### Querying via Python

```python
from rail_django.extensions.audit.models import AuditLog

# Find all actions by a specific user
logs = AuditLog.objects.filter(actor=user).order_by("-timestamp")

for log in logs:
    print(f"{log.timestamp}: {log.operation_name} - {log.variables}")
```

### Querying via GraphQL

Rail Django exposes an `auditLogList` query if the schema is configured to include it.

```graphql
query {
  auditLogList(filters: { actor: { username: "admin" } }) {
    timestamp
    operationName
    variables
    clientIp
  }
}
```

## Custom Logger

If you want to send logs to ELK, Splunk, or Datadog instead of the DB, you can listen to the `audit_log_record` signal.

```python
from django.dispatch import receiver
from rail_django.extensions.audit.signals import audit_log_record

@receiver(audit_log_record)
def send_to_splunk(sender, log_entry, **kwargs):
    splunk_client.send({
        "event": "graphql_audit",
        "user": log_entry.username,
        "query": log_entry.query_body
    })
```
