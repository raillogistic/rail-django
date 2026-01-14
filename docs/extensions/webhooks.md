# Webhooks Extension

Module: `rail_django.webhooks`

- Async HTTP delivery for model created/updated/deleted events.
- Configure via `RAIL_DJANGO_GRAPHQL["webhook_settings"]` or `RAIL_DJANGO_WEBHOOKS`.
- Optional HMAC signing via `X-Rail-Signature` headers.
- Full reference: [guides/webhooks](../guides/webhooks.md).
