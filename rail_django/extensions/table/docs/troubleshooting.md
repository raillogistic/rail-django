# Table v3 Troubleshooting

## Cache or version mismatch

1. Compare `configVersion`, `modelSchemaVersion`, and `deployVersion` from bootstrap.
2. Invalidate keys starting with `table:bootstrap:<app>:<model>` and retry.
3. If mismatch persists, run `python manage.py generate_v3_config`.

## Retryable action errors

- Check `retryable` and `retryAfter` fields in mutation errors.
- Backoff client retries and inspect rate limiter thresholds.
