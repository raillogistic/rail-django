# Complete Configuration

Rail Django is highly configurable via the `RAIL_DJANGO_GRAPHQL` dictionary in your project's `settings.py`. This document serves as the authoritative reference for all available configuration options.

## General Structure

Settings are grouped into logical sections. You only need to define the sections and keys you wish to override from the defaults.

```python
# settings.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": { ... },
    "query_settings": { ... },
    "mutation_settings": { ... },
    "security_settings": { ... },
    "performance_settings": { ... },
    "middleware_settings": { ... },
    "error_handling": { ... },
}
```

## Schema Settings (`schema_settings`)

Controls global schema behavior and discovery.

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `auto_camelcase` | `bool` | `True` | Automatically convert snake_case Python names to camelCase GraphQL names. |
| `enable_introspection` | `bool` | `True` | Enable the `__schema` and `__type` queries. |
| `enable_graphiql` | `bool` | `True` | Enable the interactive GraphiQL IDE. |
| `authentication_required` | `bool` | `False` | Require a valid user for ALL GraphQL operations by default. |
| `show_metadata` | `bool` | `False` | Enable the Schema Metadata extension. |
| `excluded_apps` | `list` | `[]` | Django apps to completely ignore during schema discovery. |
| `query_extensions` | `list` | `[]` | Dotted paths to additional Query classes to merge into the root schema. |
| `mutation_extensions` | `list` | `[]` | Dotted paths to additional Mutation classes. |

## Query Settings (`query_settings`)

Configures how data is fetched and presented.

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `default_page_size` | `int` | `20` | Items returned per page when no limit is specified. |
| `max_page_size` | `int` | `100` | Hard limit on items per page. |
| `use_relay` | `bool` | `False` | Use Relay-style Connections instead of simple lists and offset pagination. |
| `require_model_permissions` | `bool` | `True` | Enforce Django model `view` permissions for queries. |
| `generate_filters` | `bool` | `True` | Automatically generate the `where` argument for list queries. |
| `additional_lookup_fields`| `dict` | `{}` | Map of models to lists of fields that can be used for single item lookups. |

## Mutation Settings (`mutation_settings`)

Configures data modification operations.

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `generate_create` | `bool` | `True` | Auto-generate `create<Model>` mutations. |
| `generate_update` | `bool` | `True` | Auto-generate `update<Model>` mutations. |
| `generate_delete` | `bool` | `True` | Auto-generate `delete<Model>` mutations. |
| `enable_bulk_operations` | `bool` | `True` | Enable bulk CUD operations. |
| `enable_nested_relations`| `bool` | `True` | Enable the "Unified Input" format for managing relationships. |
| `require_model_permissions`| `bool` | `True` | Enforce `add`, `change`, and `delete` permissions. |
| `enable_method_mutations` | `bool` | `True` | Allow exposing model methods as mutations via `GraphQLMeta`. |

## Security Settings (`security_settings`)

Controls the security posture and validation.

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `enable_authentication` | `bool` | `True` | Integrate with Django's authentication system. |
| `enable_authorization` | `bool` | `True` | Enable granular RBAC and operation guards. |
| `enable_field_permissions`| `bool` | `True` | Enable field-level visibility and access control. |
| `enable_policy_engine` | `bool` | `True` | Enable the allow/deny policy manager. |
| `enable_input_validation`| `bool` | `True` | Sanitize and validate all incoming GraphQL inputs. |
| `enable_rate_limiting` | `bool` | `False` | Enable request rate limiting. |

## Performance Settings (`performance_settings`)

Optimizes database and query execution.

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `enable_select_related` | `bool` | `True` | Automatically optimize ForeignKey relationships. |
| `enable_prefetch_related`| `bool` | `True` | Automatically optimize ManyToMany relationships. |
| `enable_dataloader` | `bool` | `True` | Use DataLoaders for batching deep relationship queries. |
| `max_query_depth` | `int` | `10` | Maximum allowed nesting depth for queries. |
| `max_query_complexity` | `int` | `1000` | Maximum allowed calculated complexity score. |

## Middleware Settings (`middleware_settings`)

Enables/disables specific middleware layers.

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `enable_performance_middleware` | `bool` | `True` | Track and log execution time. |
| `enable_logging_middleware` | `bool` | `True` | Log GraphQL operations and errors. |
| `log_queries` | `bool` | `True` | Log query operations. |
| `log_mutations` | `bool` | `True` | Log mutation operations. |
| `log_field_level` | `bool` | `False` | Log non-root field resolutions (very verbose). |
| `log_introspection` | `bool` | `False` | Log introspection fields (`__schema`, `__type`, `__typename`). |
| `log_errors` | `bool` | `True` | Log errors during field resolution. |
| `performance_threshold_ms` | `int` | `1000` | Threshold for logging "slow" queries. |

## Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `GRAPHQL_PERFORMANCE_HEADERS` | Include execution metrics in HTTP headers. | `False` |
| `JWT_SECRET_KEY` | Key used for signing JWT tokens. | `SECRET_KEY` |

## See Also

- [Queries Reference](./queries.md)
- [Mutations Reference](./mutations.md)
- [Performance Optimization](./performance.md)
