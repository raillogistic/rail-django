# Migration overview

This guide summarizes notable changes and new configuration knobs.

## New Features

- Persisted queries (APQ) with allowlist support (`persisted_query_settings`).
- Schema snapshots, export, and diff endpoints (`schema_registry` settings).
- Plugin execution hooks (`plugin_settings` and `GRAPHQL_SCHEMA_PLUGINS`).
- Observability plugins for Sentry/OpenTelemetry (optional).
- Optional GraphQL subscriptions helper (Channels).

## Settings Additions

Add these sections to `RAIL_DJANGO_GRAPHQL` as needed:

```python
RAIL_DJANGO_GRAPHQL = {
    "persisted_query_settings": {
        "enabled": False,
        "cache_alias": "default",
        "ttl": 86400,
        "allow_unregistered": True,
        "enforce_allowlist": False,
        "allowlist": {},
        "allowlist_path": None,
        "hash_algorithm": "sha256",
        "max_query_length": 0,
    },
    "plugin_settings": {
        "enable_schema_hooks": True,
        "enable_execution_hooks": True,
    },
    "schema_registry": {
        "enable_schema_snapshots": False,
        "snapshot_max_entries": 50,
        "enable_schema_export": True,
        "enable_schema_diff": True,
    },
}
```

## REST API Additions

New schema registry endpoints:

- `GET /api/v1/schemas/<schema_name>/export/`
- `GET /api/v1/schemas/<schema_name>/history/`
- `GET /api/v1/schemas/<schema_name>/diff/`

## Optional Dependencies

- `Django Channels` for subscriptions.
- `sentry-sdk` and `opentelemetry-api` for observability plugins.

## Notes

- Persisted queries are disabled by default; enable explicitly per schema.
- Schema snapshots are disabled by default; enable to power history/diff endpoints.
