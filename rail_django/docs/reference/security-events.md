# Security events reference

## Overview

Rail Django provides a unified security event system for audit logging,
anomaly detection, and observability.

## Quick Start

```python
from rail_django.security import security, EventType, Outcome

# Log a custom event
security.emit(
    EventType.DATA_READ,
    request=request,
    resource_type="model",
    resource_name="User",
    resource_id="123"
)

# Use convenience methods
security.auth_failure(request, username="admin", reason="Invalid password")
security.permission_denied(request, "model", "SensitiveData", "read")
security.query_blocked(request, "complexity", {"score": 150, "max": 100})
```

## Event Types

| Category | Event Type | Description |
|----------|------------|-------------|
| auth | AUTH_LOGIN_SUCCESS | Successful login |
| auth | AUTH_LOGIN_FAILURE | Failed login attempt |
| authz | AUTHZ_PERMISSION_DENIED | Access denied |
| data | DATA_SENSITIVE_ACCESS | Sensitive field accessed |
| query | QUERY_BLOCKED_COMPLEXITY | Query rejected |
| rate | RATE_LIMIT_EXCEEDED | Rate limit hit |

## Anomaly Detection

Requires Redis for distributed counting:

```python
SECURITY_REDIS_URL = "redis://localhost:6379/0"
```

Automatically detects:
- Brute force login attempts (per IP and per user)
- Rate limit violations
- Auto-blocks offending IPs

## Custom Sinks

```python
from rail_django.security.events.sinks.base import EventSink
from rail_django.security.events.bus import get_event_bus

class SlackSink(EventSink):
    def write(self, event):
        if event.severity.value in ("error", "critical"):
            send_slack_alert(event.to_dict())

get_event_bus().add_sink(SlackSink())
```
