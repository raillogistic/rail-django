# Audit logging extension

The audit logging extension records security and activity events so you can
trace access, investigate failures, and export compliance evidence. This page
covers the runtime event model, configuration, and operational commands that
exist in the current `rail-django` codebase.

## What the extension records

Audit entries are stored as `AuditEventModel` records and are emitted through
the security event API. Events include actor identity, request metadata,
outcome, severity, and optional structured context.

By default, Rail Django audits all GraphQL mutations. Query audit entries are
opt-in. Add the root query field name or GraphQL operation name to
`security_settings.audited_query_fields` when you want a query recorded.

The persisted model lives in `rail_django.extensions.audit.models` and includes
fields such as:

- `event_type`
- `severity`
- `user_id` and `username`
- `client_ip` and `user_agent`
- `timestamp`
- `request_path` and `request_method`
- `additional_data`
- `success` and `error_message`

## Configure audit behavior

Audit behavior is controlled through Django settings consumed by
`rail_django.security.config.SecurityConfig`.

```python
# settings.py
GRAPHQL_ENABLE_AUDIT_LOGGING = True
AUDIT_STORE_IN_DATABASE = True
AUDIT_STORE_IN_FILE = True
AUDIT_WEBHOOK_URL = None
AUDIT_RETENTION_DAYS = 90

RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        # Mutations are always audited when audit logging is enabled.
        # Add root query field names or GraphQL operation names here to audit
        # specific queries too.
        "audited_query_fields": ["me", "CustomerSearch"],
        # Apply depth and complexity limits only to these queries.
        "limited_query_fields": ["me", "CustomerSearch"],
    }
}

AUDIT_ALERT_THRESHOLDS = {
    "failed_logins_per_ip": 10,
    "failed_logins_per_user": 5,
    "suspicious_activity_window": 300,
}
```

## Emit audit events from backend code

Use the unified security API to emit events from your code.

```python
from rail_django.security import security, EventType, Outcome, Severity

security.emit(
    EventType.AUTH_LOGIN_FAILURE,
    request=request,
    outcome=Outcome.FAILURE,
    severity=Severity.WARNING,
    action="Login attempt failed",
    context={"username_attempted": username},
    error="Invalid credentials",
)
```

## Record frontend actions

When extension mutations are enabled in schema settings, Rail Django exposes
`logFrontendAudit` through `LogFrontendAuditMutation`.

```graphql
mutation LogFrontendAudit($input: FrontendAuditEventInput!) {
  logFrontendAudit(input: $input) {
    ok
    error
  }
}
```

Example input payload:

```json
{
  "appName": "admin",
  "modelName": "Order",
  "operation": "approve",
  "component": "OrderApprovalDialog",
  "severity": "medium",
  "success": true,
  "metadata": {"orderId": "123"}
}
```

## Operate and retain audit data

Use the `audit_management` command for export, cleanup, and summary operations.

```bash
python manage.py audit_management export --format json --days 30 --output audit.json
python manage.py audit_management cleanup --days 180 --dry-run
python manage.py audit_management summary --hours 24
```

## Query stored events directly

You can inspect records directly through Django ORM.

```python
from rail_django.extensions.audit.models import get_audit_event_model

AuditEvent = get_audit_event_model()
recent = AuditEvent.objects.filter(success=False).order_by("-timestamp")[:50]
```

Mutation audit rows are stored as `data.create`, `data.update`, `data.delete`,
or `data.bulk` events. Query audit rows are stored as `data.read` when the
query matches `security_settings.audited_query_fields`.

## Next steps

After enabling audit logging, run `python manage.py security_check --verbose`
and review the [security reference](../reference/security.md).
