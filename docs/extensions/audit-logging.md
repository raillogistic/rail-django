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