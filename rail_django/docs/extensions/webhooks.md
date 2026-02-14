# Webhooks

Rail Django includes a powerful webhook system that lets you notify external services in real-time when events occur in your application.

## Overview

The webhook system provides:
- Automated event dispatching based on model changes (created, updated, deleted).
- Support for multiple endpoints with specific model and event filters.
- Secure delivery with HMAC signatures (`X-Webhook-Signature`).
- Asynchronous delivery using background workers (Celery, Dramatiq, etc.).
- Automatic retries with exponential backoff.
- Detailed delivery logs and error tracking.

## Configuration

### Basic Configuration
Enable webhooks and define your endpoints in your settings:

```python
RAIL_DJANGO_WEBHOOKS = {
    "enabled": True,
    "endpoints": [
        {
            "name": "primary_crm",
            "url": "https://crm.example.com/webhooks/",
            "secret": "your-signing-secret",
            "events": ["created", "updated"],
            "include_models": ["store.Order", "store.Customer"],
        },
    ],
    "async_delivery": True,
    "max_retries": 3,
}
```

### Advanced Configuration
For more complex setups, you can use a `webhooks.py` file or the `WebhookConfig` object.

```python
# root/webhooks.py
from rail_django.webhooks import WebhookConfig, WebhookEndpoint

WEBHOOKS = WebhookConfig(
    enabled=True,
    endpoints=[
        WebhookEndpoint(
            name="analytics",
            url="https://analytics.example.com/events/",
            secret="secret_123",
            include_models=["store.Order"],
            include_fields=["id", "total", "status"],
        ),
    ],
)
```

## Dispatching Events

### Automatic Dispatch
By default, Rail Django can automatically dispatch events when models are saved or deleted if they are included in an endpoint's `include_models` list.

### Manual Dispatch
You can manually trigger events from your code, such as from Django signals:

```python
from rail_django.webhooks import dispatch_model_event

@receiver(post_save, sender=Order)
def order_paid(sender, instance, **kwargs):
    if instance.is_paid:
        dispatch_model_event("order.paid", instance)
```

## Payload Structure

Webhooks send a JSON payload containing the event type, timestamp, and the serialized object.

```json
{
  "id": "evt_abc123",
  "event": "order.paid",
  "timestamp": "2026-01-24T10:00:00Z",
  "model": {
    "app": "store",
    "name": "Order"
  },
  "object": {
    "id": "42",
    "reference": "ORD-123",
    "total": "150.00",
    "status": "PAID"
  },
  "changes": {
    "status": { "old": "PENDING", "new": "PAID" }
  },
  "user": {
    "id": "1",
    "username": "admin"
  }
}
```

## Security & Verification

Every webhook request includes an `X-Webhook-Signature` header. The receiver should verify this signature using the shared secret and HMAC-SHA256.

### Verification Example (Node.js)
```javascript
const crypto = require('crypto');

function verifyWebhook(secret, payload, signature, timestamp) {
  const message = `${timestamp}.${payload}`;
  const expected = 'sha256=' + crypto.createHmac('sha256', secret)
    .update(message)
    .digest('hex');
  return crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
}
```

## Filtering and Redaction

You can control exactly what data is sent to each endpoint:

```python
WebhookEndpoint(
    name="external_partner",
    url="https://partner.com/api/",
    # Only include these fields
    include_fields={"store.Order": ["id", "reference", "total"]},
    # Or redact sensitive information
    redact_fields={"store.Customer": {"email": "***@***.com"}},
)
```

## Best Practices

1. **Use Secrets**: Always use a unique, strong secret for each endpoint and store it in environment variables.
2. **Respond Quickly**: Return a `200 OK` immediately and process the webhook payload asynchronously on your end.
3. **Verify Signatures**: Never process a webhook without verifying its signature.
4. **Implement Idempotency**: Use the `X-Webhook-Event-Id` to avoid processing the same event multiple times.

## See Also

- [Subscriptions](./subscriptions.md) - For real-time updates over WebSockets.
- [Audit Logging](./audit-logging.md) - For tracking internal system events.
- [Background Tasks](./tasks.md) - For how webhooks are delivered asynchronously.
