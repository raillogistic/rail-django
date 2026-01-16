# Webhooks

## Overview

Rail Django includes a webhook system for sending events to external systems when data changes occur. This guide covers configuration, payload structure, security, and best practices.

---

## Table of Contents

1. [Configuration](#configuration)
2. [Payload Structure](#payload-structure)
3. [Model Filtering](#model-filtering)
4. [Field Filtering and Redaction](#field-filtering-and-redaction)
5. [HMAC Signature](#hmac-signature)
6. [Endpoint Authentication](#endpoint-authentication)
7. [Asynchronous Delivery](#asynchronous-delivery)
8. [Retries and Error Handling](#retries-and-error-handling)
9. [Complete Examples](#complete-examples)
10. [Best Practices](#best-practices)

---

## Configuration

### Basic Configuration

```python
# root/settings/base.py
RAIL_DJANGO_WEBHOOKS = {
    # Activation
    "enabled": True,

    # Endpoints
    "endpoints": [
        {
            "name": "main",
            "url": "https://example.com/webhooks/",
            "secret": os.environ.get("WEBHOOK_SECRET"),
            "events": ["created", "updated", "deleted"],
        },
    ],

    # Delivery options
    "async_delivery": True,
    "timeout_seconds": 30,
    "max_retries": 3,
    "retry_delay_seconds": 60,
}
```

### webhooks.py File

For complex configurations, use `root/webhooks.py`:

```python
# root/webhooks.py
from rail_django.webhooks import WebhookConfig, WebhookEndpoint

WEBHOOKS = WebhookConfig(
    enabled=True,
    endpoints=[
        WebhookEndpoint(
            name="crm",
            url="https://crm.example.com/api/webhooks/",
            secret="secret_crm_123",
            include_models=["store.Customer", "store.Order"],
            events=["created", "updated"],
        ),
        WebhookEndpoint(
            name="analytics",
            url="https://analytics.example.com/events/",
            secret="secret_analytics_456",
            include_models=["store.Order"],
            events=["created"],
            include_fields=["id", "total", "status", "created_at"],
        ),
    ],
)
```

---

## Payload Structure

### Event Payload

```json
{
  "id": "evt_abc123xyz",
  "event": "created",
  "timestamp": "2026-01-16T12:00:00Z",
  "model": {
    "app": "store",
    "name": "Order",
    "label": "store.Order"
  },
  "object": {
    "id": "42",
    "reference": "ORD-2026-0042",
    "status": "pending",
    "total": "299.99",
    "customer": {
      "id": "15",
      "name": "John Doe"
    },
    "created_at": "2026-01-16T11:59:00Z"
  },
  "changes": null,
  "user": {
    "id": "1",
    "username": "admin"
  }
}
```

### Update Payload (with changes)

```json
{
  "id": "evt_def456abc",
  "event": "updated",
  "timestamp": "2026-01-16T12:30:00Z",
  "model": {
    "app": "store",
    "name": "Order",
    "label": "store.Order"
  },
  "object": {
    "id": "42",
    "reference": "ORD-2026-0042",
    "status": "shipped",
    "total": "299.99"
  },
  "changes": {
    "status": {
      "old": "pending",
      "new": "shipped"
    }
  },
  "user": {
    "id": "1",
    "username": "admin"
  }
}
```

---

## Model Filtering

### Include Specific Models

```python
WebhookEndpoint(
    name="orders",
    url="https://example.com/webhooks/orders/",
    secret="secret_123",
    include_models=["store.Order", "store.OrderItem"],
)
```

### Exclude Models

```python
WebhookEndpoint(
    name="all_except_logs",
    url="https://example.com/webhooks/",
    secret="secret_123",
    exclude_models=["audit.AuditEvent", "sessions.Session"],
)
```

### Per-Model Configuration

```python
class Order(models.Model):
    class WebhookMeta:
        # Enable webhooks for this model
        enabled = True

        # Triggered events
        events = ["created", "updated"]  # exclude "deleted"

        # Condition for sending
        def should_send(self, instance, event):
            # Only send for completed orders
            if event == "updated":
                return instance.status == "completed"
            return True
```

---

## Field Filtering and Redaction

### Include Specific Fields

```python
WebhookEndpoint(
    name="minimal",
    url="https://example.com/webhooks/",
    secret="secret_123",
    include_fields={
        "store.Order": ["id", "reference", "status", "total"],
        "store.Customer": ["id", "name", "email"],
    },
)
```

### Exclude Fields

```python
WebhookEndpoint(
    name="safe",
    url="https://example.com/webhooks/",
    secret="secret_123",
    exclude_fields={
        "*": ["password", "token", "secret"],  # All models
        "store.Customer": ["ssn", "credit_card"],
    },
)
```

### Redact Sensitive Fields

```python
WebhookEndpoint(
    name="redacted",
    url="https://example.com/webhooks/",
    secret="secret_123",
    redact_fields={
        "store.Customer": {
            "email": "***@***.com",
            "phone": "***-***-****",
        },
    },
)
```

Result:

```json
{
  "object": {
    "id": "15",
    "name": "John Doe",
    "email": "***@***.com",
    "phone": "***-***-****"
  }
}
```

---

## HMAC Signature

### Signature Generation

Each request includes a signature for verification:

```http
POST /webhooks/ HTTP/1.1
Host: example.com
Content-Type: application/json
X-Webhook-Signature: sha256=a1b2c3d4e5f6...
X-Webhook-Timestamp: 1705405200
X-Webhook-Event-Id: evt_abc123xyz
```

### Verification (Python)

```python
import hmac
import hashlib

def verify_webhook(request, secret):
    """
    Verifies webhook signature.

    Args:
        request: HTTP request.
        secret: Shared secret.

    Returns:
        True if signature is valid.
    """
    signature = request.headers.get("X-Webhook-Signature")
    timestamp = request.headers.get("X-Webhook-Timestamp")

    if not signature or not timestamp:
        return False

    # Build message
    message = f"{timestamp}.{request.body.decode()}"

    # Calculate expected signature
    expected = "sha256=" + hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)
```

### Verification (Node.js)

```javascript
const crypto = require("crypto");

function verifyWebhook(req, secret) {
  const signature = req.headers["x-webhook-signature"];
  const timestamp = req.headers["x-webhook-timestamp"];

  if (!signature || !timestamp) return false;

  const message = `${timestamp}.${req.body}`;
  const expected =
    "sha256=" +
    crypto.createHmac("sha256", secret).update(message).digest("hex");

  return crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
}
```

---

## Endpoint Authentication

### Static Token

```python
WebhookEndpoint(
    name="with_token",
    url="https://example.com/webhooks/",
    secret="signature_secret",
    headers={
        "Authorization": "Bearer static_token_xyz",
    },
)
```

### OAuth2

```python
WebhookEndpoint(
    name="oauth2",
    url="https://example.com/webhooks/",
    secret="signature_secret",
    auth={
        "type": "oauth2",
        "client_id": os.environ.get("OAUTH_CLIENT_ID"),
        "client_secret": os.environ.get("OAUTH_CLIENT_SECRET"),
        "token_url": "https://auth.example.com/oauth/token",
        "scope": "webhooks:write",
    },
)
```

---

## Asynchronous Delivery

### Configuration

```python
RAIL_DJANGO_WEBHOOKS = {
    "async_delivery": True,
    "async_backend": "celery",  # "celery", "dramatiq", "django_q"
    "queue": "webhooks",
}
```

### Celery Task

```python
# Automatically created task
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def deliver_webhook(self, endpoint_name, payload):
    # ... delivery logic
```

---

## Retries and Error Handling

### Retry Configuration

```python
WebhookEndpoint(
    name="resilient",
    url="https://example.com/webhooks/",
    secret="secret_123",
    retry_config={
        "max_retries": 5,
        "retry_delay": 60,  # seconds
        "backoff_factor": 2,  # exponential
        "max_delay": 3600,  # 1 hour max
        "retry_on_status": [429, 500, 502, 503, 504],
    },
)
```

### Error Handling

```python
RAIL_DJANGO_WEBHOOKS = {
    "on_failure": "log",  # "log", "raise", "callback"
    "failure_callback": "myapp.webhooks.on_webhook_failed",
}

# myapp/webhooks.py
def on_webhook_failed(endpoint, payload, error, attempt):
    """
    Called when a webhook definitively fails.
    """
    send_alert(
        f"Webhook failed: {endpoint.name}",
        details={
            "error": str(error),
            "attempts": attempt,
            "payload": payload,
        }
    )
```

### Webhook Logs

```graphql
query WebhookLogs {
  webhook_logs(endpoint: "orders", status: "failed", limit: 50) {
    id
    endpoint_name
    event_type
    payload
    status
    status_code
    error_message
    attempts
    created_at
    completed_at
  }
}
```

---

## Complete Examples

### ERP Synchronization

```python
# root/webhooks.py
WebhookEndpoint(
    name="erp_sync",
    url="https://erp.company.com/api/webhooks/",
    secret=os.environ.get("ERP_WEBHOOK_SECRET"),
    include_models=[
        "store.Product",
        "store.Order",
        "inventory.StockMovement",
    ],
    events=["created", "updated"],
    include_fields={
        "store.Product": ["id", "sku", "name", "price", "stock_quantity"],
        "store.Order": ["id", "reference", "status", "total", "items"],
    },
    headers={
        "X-API-Key": os.environ.get("ERP_API_KEY"),
    },
)
```

### Notification Service

```python
WebhookEndpoint(
    name="notifications",
    url="https://notifications.example.com/events/",
    secret=os.environ.get("NOTIF_SECRET"),
    include_models=["store.Order"],
    events=["created", "updated"],
    transform=lambda payload: {
        "type": f"order_{payload['event']}",
        "order_id": payload["object"]["id"],
        "customer_email": payload["object"]["customer"]["email"],
        "status": payload["object"]["status"],
    },
)
```

---

## Best Practices

### 1. Use Secrets

```python
# ✅ Use environment variables
"secret": os.environ.get("WEBHOOK_SECRET"),

# ❌ Avoid hardcoded secrets
"secret": "my_secret_123",
```

### 2. Always Verify Signatures

```python
if not verify_webhook(request, secret):
    return HttpResponse(status=401)
```

### 3. Respond Quickly

```python
# ✅ Return 200 immediately, process later
def webhook_handler(request):
    verify_webhook(request, secret)
    process_async.delay(request.body)
    return HttpResponse(status=200)
```

### 4. Implement Idempotency

```python
def handle_webhook(request):
    event_id = request.headers.get("X-Webhook-Event-Id")

    # Check if already processed
    if WebhookLog.objects.filter(event_id=event_id).exists():
        return HttpResponse(status=200)  # Already processed

    # Process event
    process_event(request.body)

    # Record as processed
    WebhookLog.objects.create(event_id=event_id)
```

### 5. Monitor Webhook Health

```python
RAIL_DJANGO_WEBHOOKS = {
    "monitoring": {
        "enabled": True,
        "alert_on_consecutive_failures": 5,
        "alert_callback": "myapp.monitoring.webhook_alert",
    },
}
```

---

## See Also

- [Subscriptions](./subscriptions.md) - Real-time with WebSocket
- [Audit & Logging](./audit.md) - Event tracking
- [Configuration](../graphql/configuration.md) - All settings
