# Schema registry

> **Module path:** `rail_django.core.registry.registry`

`SchemaRegistry` manages named schema definitions, schema builders, and schema
instance caches.

## Responsibilities

`SchemaRegistry` provides:

- Named schema registration via `register_schema(...)`
- Schema lookup and listing (`get_schema`, `list_schemas`, `get_schema_names`)
- Builder access and caching (`get_schema_builder`, `get_schema_instance`)
- Schema discovery hooks and auto-discovery execution
- Runtime schema enable and disable controls

## Register schema definitions

```python
from rail_django.core.registry import schema_registry

schema_registry.register_schema(
    name="admin",
    description="Admin API",
    apps=["users", "orders"],
    settings={
        "schema_settings": {
            "authentication_required": True,
            "enable_graphiql": False,
        }
    },
)
```

## Access schema metadata

```python
info = schema_registry.get_schema("admin")
all_infos = schema_registry.list_schemas(enabled_only=True)
```

## Resolve models for a schema

`get_models_for_schema(name)` resolves models from configured app labels,
then applies `models` and `exclude_models` filters in the schema definition.

## Builder and instance caching

Registry methods coordinate builder and schema instance lifecycles:

- `get_schema_builder(name)`
- `get_cached_schema_builder(name)`
- `get_schema_instance(name)`
- `clear_builders()`
- `clear()`

## Validate schema definitions

Use `validate_schema(name)` to check app availability and model coverage.

## Discovery hooks

Registry supports registration hooks and discovery hooks:

- `add_pre_registration_hook(...)`
- `add_post_registration_hook(...)`
- `add_discovery_hook(...)`

## Next steps

- [Schema builder](./schema-builder.md)
- [Core configuration](../../core/configuration.md)
- [Runtime API reference](../../reference/api.md)
