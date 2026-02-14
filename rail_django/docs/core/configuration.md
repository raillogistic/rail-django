# Core configuration

Rail Django reads runtime configuration from `RAIL_DJANGO_GRAPHQL`, then merges
that data with library defaults from `rail_django.config.defaults`.

This page focuses on settings actively consumed by the current codebase.

## Configure by section

Define only the sections you need in `settings.py`.

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {},
    "type_generation_settings": {},
    "query_settings": {},
    "filtering_settings": {},
    "mutation_settings": {},
    "subscription_settings": {},
    "performance_settings": {},
    "security_settings": {},
    "middleware_settings": {},
    "persisted_query_settings": {},
    "multitenancy_settings": {},
    "error_handling": {},
}
```

## `schema_settings`

Use this section to control root schema behavior and exposure.

Common keys:

- `authentication_required` (default: `False`)
- `enable_introspection` (default: `True`)
- `enable_graphiql` (default: `True`)
- `auto_camelcase` (default: `True`)
- `excluded_apps` and `excluded_models`
- `enable_extension_mutations` (default: `True`)
- `query_field_allowlist`, `mutation_field_allowlist`,
  `subscription_field_allowlist`

## `query_settings`

Use this section to tune list/read behavior.

Common keys:

- `default_page_size` (default: `20`)
- `max_page_size` (default: `100`)
- `use_relay` (default: `False`)
- `generate_filters` (default: `True`)
- `generate_ordering` (default: `True`)
- `require_model_permissions` (default: `True`)
- `model_permission_codename` (default: `"view"`)

## `mutation_settings`

Use this section to control generated mutation behavior.

Common keys:

- `generate_create`, `generate_update`, `generate_delete`
- `enable_bulk_operations` (default: `True`)
- `enable_method_mutations` (default: `True`)
- `require_model_permissions` (default: `True`)
- `model_permission_codenames` (create/add, update/change, delete/delete)
- `enable_nested_relations` (default: `True`)
- `relation_max_nesting_depth` (default: `3`)

## `performance_settings`

Use this section for query optimization and guardrails.

Common keys:

- `enable_select_related`, `enable_prefetch_related`
- `enable_query_optimization`
- `max_query_depth` (default: `10`)
- `max_query_complexity` (default: `1000`)
- `query_timeout` (default: `30`)
- `enable_query_caching` and `query_cache_timeout`

## `security_settings`

Use this section for authorization, validation, and request controls.

Common keys:

- `enable_authentication`
- `enable_authorization`
- `enable_policy_engine`
- `enable_field_permissions`
- `enable_input_validation`
- `enable_sql_injection_protection`
- `enable_xss_protection`
- `enable_rate_limiting`
- `permission_cache_ttl_seconds`
- `input_allowed_html_tags` and `input_allowed_html_attributes`

## `middleware_settings`

Use this section to toggle middleware behavior and logging detail.

Common keys:

- `enable_authentication_middleware`
- `enable_rate_limiting_middleware`
- `enable_field_permission_middleware`
- `enable_logging_middleware`
- `log_queries`, `log_mutations`, `log_errors`
- `performance_threshold_ms`

## Extension-specific settings

Some extensions read dedicated top-level settings in addition to
`RAIL_DJANGO_GRAPHQL`.

Examples:

- `RAIL_DJANGO_EXPORT`
- `GRAPHQL_ENABLE_AUDIT_LOGGING`
- `AUDIT_STORE_IN_DATABASE`, `AUDIT_STORE_IN_FILE`, `AUDIT_RETENTION_DAYS`
- `JWT_*` and `MFA_*` keys for auth flows

## Validate your configuration

After changing settings, run security and runtime checks.

```bash
python manage.py security_check --verbose
python manage.py health_monitor --summary-only
```

## Next steps

Continue with [performance](./performance.md), [mutations](./mutations.md), and
[security reference](../reference/security.md).
