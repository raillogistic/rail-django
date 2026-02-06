# Table v3 Security

- Validate and sanitize all action payloads server-side.
- Enforce per-subject rate limits for table mutations.
- Mask sensitive fields before they reach the client.
- Emit audit events for create/update/delete/export operations.
- Apply CSP headers on table rendering endpoints.
