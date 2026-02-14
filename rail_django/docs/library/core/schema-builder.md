# Schema builder

> **Module path:** `rail_django.core.schema`

`SchemaBuilder` assembles GraphQL schema objects from discovered Django models,
registered extensions, and schema-specific settings.

## What `SchemaBuilder` does

`SchemaBuilder` composes multiple mixins to provide:

- Model discovery and schema lifecycle (`SchemaBuilderCore`)
- Query and mutation generation (`QueryBuilderMixin`)
- Extension integration (`ExtensionsMixin`)
- Registration helpers (`RegistrationMixin`)
- Additional query integration (`QueryIntegrationMixin`)

## Create and access builders

Use the high-level API exported by `rail_django.core.schema`.

```python
from rail_django.core.schema import get_schema_builder, get_schema

builder = get_schema_builder("default")
schema = builder.get_schema()

# shortcut
schema = get_schema("default")
```

## Main runtime methods

Common `SchemaBuilder` operations:

- `get_schema(model_list=None)`
- `rebuild_schema()`
- `clear_schema()`
- `get_schema_version()`
- `get_registered_models()`
- `register_mutation(mutation_class, name=None)`

## Schema-scoped behavior

Builders read settings through the schema name and runtime settings proxy.
That means `get_schema_builder("admin")` can produce a different schema than
`get_schema_builder("default")`.

Settings are merged from library defaults, optional environment overrides,
registry-provided overrides, and your Django settings.

## Global schema helpers

`rail_django.core.schema` also exports global helpers:

- `get_schema_builder(schema_name)`
- `get_schema(schema_name)`
- `register_mutation(mutation_class, name=None, schema_name="default")`
- `clear_all_schemas()`
- `get_all_schema_names()`

## Next steps

- [Schema registry](./schema-registry.md)
- [GraphQLMeta reference](./graphql-meta.md)
- [Core configuration](../../core/configuration.md)
