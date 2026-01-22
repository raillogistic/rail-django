# Configuration

Rail Django is highly configurable via the `RAIL_DJANGO_GRAPHQL` setting in your project's `settings.py`.

## Structure

The configuration is a nested dictionary grouped by feature area.

```python
# settings.py

RAIL_DJANGO_GRAPHQL = {
    "schema_settings": { ... },
    "security_settings": { ... },
    "performance_settings": { ... },
    # ...
}
```

## Reference

### Schema Settings (`schema_settings`)

Controls the general behavior of the generated schema.

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `auto_camelcase` | `bool` | `True` | Convert snake_case Python fields to camelCase GraphQL fields. |
| `enable_introspection` | `bool` | `True` | Allow schema introspection (queries to `__schema`). |
| `enable_graphiql` | `bool` | `True` | Enable the GraphiQL IDE interface. |
| `graphiql_superuser_only` | `bool` | `False` | Restrict GraphiQL access to superusers. |
| `enable_pagination` | `bool` | `True` | Enable pagination by default on list queries. |
| `authentication_required` | `bool` | `False` | Require authentication for all queries by default. |
| `disable_security_mutations` | `bool` | `False` | specific security mutations (login, etc.). |

### Query Settings (`query_settings`)

Controls how data is fetched.

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `default_page_size` | `int` | `20` | Default number of items per page. |
| `max_page_size` | `int` | `100` | Maximum items allowed per page. |
| `use_relay` | `bool` | `False` | Use Relay-style connections (Edges/Nodes) instead of offset pagination. |
| `require_model_permissions` | `bool` | `True` | Enforce Django model `view` permissions for queries. |

### Mutation Settings (`mutation_settings`)

Controls data modification.

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `generate_create` | `bool` | `True` | Auto-generate create mutations. |
| `generate_update` | `bool` | `True` | Auto-generate update mutations. |
| `generate_delete` | `bool` | `True` | Auto-generate delete mutations. |
| `generate_bulk` | `bool` | `False` | Generate bulk CUD operations (e.g., `bulkUserCreate`). |
| `enable_nested_relations` | `bool` | `True` | Allow creating/updating related objects in a single mutation. |
| `require_model_permissions` | `bool` | `True` | Enforce Django model `add/change/delete` permissions. |

### Security Settings (`security_settings`)

Controls the security posture.

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `enable_authentication` | `bool` | `True` | Enable authentication integration. |
| `enable_query_depth_limiting` | `bool` | `True` | Block queries deeper than `max_query_depth`. |
| `enable_input_validation` | `bool` | `True` | Sanitize strings and validate inputs. |
| `enable_sql_injection_protection`| `bool` | `True` | Scan inputs for SQL injection patterns. |
| `enable_rate_limiting` | `bool` | `False` | Enable request rate limiting. |
| `introspection_roles` | `list` | `['admin', 'developer']` | Roles allowed to perform introspection if restricted. |

### Performance Settings (`performance_settings`)

Controls optimization features.

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `enable_select_related` | `bool` | `True` | Auto-optimize ForeignKey fetches. |
| `enable_prefetch_related` | `bool` | `True` | Auto-optimize ManyToMany fetches. |
| `enable_n_plus_one_detection` | `bool` | `True` | Log warnings when N+1 queries are detected. |
| `max_query_depth` | `int` | `10` | Maximum allowed query nesting depth. |
| `max_query_complexity` | `int` | `1000` | Maximum allowed query complexity score. |

### Filtering Settings (`filtering_settings`)

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `max_filter_depth` | `int` | `5` | Maximum depth for relationship filters (e.g., `user__profile__group__name`). |
| `enable_full_text_search` | `bool` | `True` | Enable PostgreSQL-specific full-text search features. |

### Multitenancy Settings (`multitenancy_settings`)

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `enabled` | `bool` | `False` | Enable multi-tenancy support. |
| `tenant_header` | `str` | `X-Tenant-ID` | HTTP header to identify the tenant. |
| `isolation_mode` | `str` | `row` | Isolation strategy (`row` or `schema`). |

### Webhook Settings (`webhook_settings`)

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `enabled` | `bool` | `False` | Enable the webhook dispatcher. |
| `signing_secret` | `str` | `None` | Secret key for HMAC signing of payloads. |
| `retry_count` | `int` | `3` | Number of retries for failed webhooks. |