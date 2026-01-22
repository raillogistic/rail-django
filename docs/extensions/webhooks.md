# Webhooks

Rail Django allows you to notify external services when events occur in your store, such as a new order being placed.

## Dispatching Events

Trigger webhooks from Django signals.

```python
from django.db.models.signals import post_save
from django.dispatch import receiver
from rail_django.webhooks import dispatch_model_event
from .models import Order, OrderStatus

@receiver(post_save, sender=Order)
def order_status_changed(sender, instance, **kwargs):
    if instance.status == OrderStatus.PAID:
        # Notifies all endpoints listening for 'order.paid'
        dispatch_model_event("order.paid", instance)
```

## Payload Content

The webhook payload includes the model data (serialized to JSON) and event metadata.

```json
{
  "event": "order.paid",
  "timestamp": "2023-10-27T10:00:00Z",
  "data": {
    "orderNumber": "ORD-123",
    "totalAmount": "150.00",
    "customer": {
      "email": "customer@example.com"
    }
  }
}
```

## Security

Every webhook request includes an `X-Rail-Signature` header, allowing the receiver to verify that the request came from your server.

### Verification Example (Node.js)

```javascript
const crypto = require('crypto');

function verifyWebhook(secret, payload, signature) {
  const hmac = crypto.createHmac('sha256', secret);
  const digest = 'sha256=' + hmac.update(payload).digest('hex');
  return crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(digest));
}
```

## Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "webhook_settings": {
        "enabled": True,
        "signing_secret": "your-secret-key",
        "retry_count": 5,
        "include_models": ["store.Order", "store.Product"]
    }
}
```