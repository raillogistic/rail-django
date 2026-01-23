# Schema Builder

> **Module Path:** `rail_django.core.schema.builder`

The SchemaBuilder is the central orchestrator of Rail Django. It coordinates model discovery, type generation, and schema assembly to produce a complete GraphQL schema from your Django models.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        SchemaBuilder                            │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│  │ TypeGenerator │   │QueryGenerator│   │MutationGenerator │   │
│  └──────────────┘   └──────────────┘   └──────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    SchemaRegistry                         │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │  │
│  │  │ default │  │  admin  │  │  auth   │  │  ...    │    │  │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                     Django Models                         │  │
│  │   Product   Order   Customer   Category   ...             │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ graphene.Schema │
                    │   Query         │
                    │   Mutation      │
                    │   Subscription  │
                    └─────────────────┘
```

## Class Reference

### SchemaBuilder

```python
from rail_django import SchemaBuilder

# Get or create a schema builder for a named schema
builder = SchemaBuilder(schema_name="default")

# Build and get the GraphQL schema
schema = builder.get_schema()

# Build with specific models only
schema = builder.get_schema(model_list=[Product, Order])
```

#### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `settings` | `SchemaSettings` | `None` | Override settings (locks settings if provided) |
| `schema_name` | `str` | `"default"` | Identifier for this schema instance |
| `raw_settings` | `dict` | `None` | Raw settings dictionary |
| `registry` | `SchemaRegistry` | `None` | Custom registry for model discovery |

#### Key Properties

| Property | Type | Description |
|----------|------|-------------|
| `type_generator` | `TypeGenerator` | Lazy-loaded type generator instance |
| `query_generator` | `QueryGenerator` | Lazy-loaded query generator instance |
| `mutation_generator` | `MutationGenerator` | Lazy-loaded mutation generator instance |
| `subscription_generator` | `SubscriptionGenerator` | Lazy-loaded subscription generator |
| `settings` | `SchemaSettings` | Current schema settings |
| `schema_name` | `str` | Name of this schema |

#### Key Methods

##### `get_schema(model_list=None) -> graphene.Schema`

Returns the current GraphQL schema, rebuilding if necessary.

```python
# Get schema with all discovered models
schema = builder.get_schema()

# Get schema with specific models only
from myapp.models import Product, Order
schema = builder.get_schema(model_list=[Product, Order])
```

##### `rebuild_schema() -> graphene.Schema`

Forces a complete schema rebuild.

```python
# Force rebuild after model changes
schema = builder.rebuild_schema()
```

##### `clear_schema() -> None`

Clears cached schema, forcing rebuild on next access.

```python
# Clear schema cache
builder.clear_schema()

# Next call will rebuild
schema = builder.get_schema()
```

##### `get_schema_version() -> int`

Returns the current schema version number (incremented on each rebuild).

```python
version = builder.get_schema_version()
print(f"Schema version: {version}")
```

##### `get_registered_models() -> Set[Type[models.Model]]`

Returns all Django models registered in this schema.

```python
models = builder.get_registered_models()
for model in models:
    print(f"Registered: {model.__name__}")
```

##### `get_query_fields() -> Dict[str, graphene.Field]`

Returns all generated query fields.

```python
fields = builder.get_query_fields()
for name, field in fields.items():
    print(f"Query: {name}")
```

##### `get_mutation_fields() -> Dict[str, Type[graphene.Mutation]]`

Returns all generated mutation classes.

```python
mutations = builder.get_mutation_fields()
for name, mutation in mutations.items():
    print(f"Mutation: {name}")
```

## Multiton Pattern

SchemaBuilder uses the Multiton pattern - one instance per schema name:

```python
from rail_django import SchemaBuilder

# These return the SAME instance
builder1 = SchemaBuilder(schema_name="default")
builder2 = SchemaBuilder(schema_name="default")
assert builder1 is builder2  # True

# This returns a DIFFERENT instance
admin_builder = SchemaBuilder(schema_name="admin")
assert builder1 is not admin_builder  # True
```

This ensures consistent schema state across your application.

## Model Discovery

The builder discovers models through two mechanisms:

### 1. Registry-Based Discovery

When a registry is provided, models are discovered from registered schemas:

```python
from rail_django.core.registry import schema_registry

# Register a schema with specific apps
schema_registry.register_schema(
    name="store",
    apps=["store", "inventory"],
    exclude_models=["HistoricalProduct"]
)

# Builder uses registry to discover models
builder = SchemaBuilder(
    schema_name="store",
    registry=schema_registry
)
```

### 2. Automatic Discovery

Without a registry, all models from `INSTALLED_APPS` are discovered:

```python
builder = SchemaBuilder(schema_name="default")
# Discovers all models from all installed apps
```

### Model Exclusion

Models are automatically excluded if they:

1. Are abstract models
2. Belong to system apps (`admin`, `contenttypes`, `sessions`)
3. Are system models (`LogEntry`)
4. Match `excluded_apps` in settings
5. Match `excluded_models` in settings
6. Are django-simple-history models (`Historical*`)

## Settings Integration

The builder integrates with the hierarchical settings system:

```python
# Settings are loaded from config_proxy
# Priority: schema_registry > RAIL_DJANGO_GRAPHQL_SCHEMAS > RAIL_DJANGO_GRAPHQL

# Access current settings
settings = builder.get_settings()
print(settings.enable_pagination)
print(settings.auto_camelcase)
```

### Settings Refresh

Settings can be refreshed at runtime (unless locked):

```python
# If settings were not provided explicitly, they can refresh
builder._refresh_settings_if_needed()

# If you provided settings explicitly, they are "locked"
builder = SchemaBuilder(
    schema_name="custom",
    settings=my_custom_settings  # Settings are locked
)
```

## Signal Handling

The builder connects to Django signals for automatic updates:

### Post-Migrate Signal

When enabled, schema rebuilds after migrations:

```python
# In settings
"schema_settings": {
    "auto_refresh_on_migration": True  # Default
}
```

### Model Change Signals

When enabled, schema rebuilds on model save/delete:

```python
# In settings (disabled by default - can be slow)
"schema_settings": {
    "auto_refresh_on_model_change": True
}
```

## Extension Points

### Custom Query Extensions

Add custom queries to the schema:

```python
# In settings
"schema_settings": {
    "query_extensions": [
        "myapp.graphql.CustomQuery",
        "myapp.graphql.ReportingQuery"
    ]
}
```

### Custom Mutation Extensions

Add custom mutations to the schema:

```python
# In settings
"schema_settings": {
    "mutation_extensions": [
        "myapp.graphql.CustomMutations",
        "myapp.graphql.AdminMutations"
    ]
}
```

## Internal Architecture

### Schema Build Flow

```
1. _discover_models()
   └── Filter by excluded_apps, excluded_models
   └── Filter out abstract and system models

2. For each model:
   └── type_generator.generate_object_type(model)
   └── type_generator.generate_input_type(model)
   └── type_generator.generate_filter_type(model)

3. For each model:
   └── query_generator.generate_single_query(model)
   └── query_generator.generate_list_query(model)
   └── query_generator.generate_paginated_query(model)

4. For each model:
   └── mutation_generator.generate_create_mutation(model)
   └── mutation_generator.generate_update_mutation(model)
   └── mutation_generator.generate_delete_mutation(model)

5. For each model (if enabled):
   └── subscription_generator.generate_subscriptions(model)

6. Merge extensions (health, metadata, custom)

7. Create graphene.Schema(query=Query, mutation=Mutation, subscription=Subscription)
```

### Thread Safety

The builder uses threading locks for safe concurrent access:

```python
class SchemaBuilderCore:
    _instances: dict[str, "SchemaBuilderCore"] = {}
    _lock = threading.Lock()

    def __new__(cls, ...):
        with cls._lock:
            if schema_name not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[schema_name] = instance
            return cls._instances[schema_name]
```

## Usage Examples

### Basic Usage

```python
from rail_django import SchemaBuilder

# Get default schema
builder = SchemaBuilder()
schema = builder.get_schema()

# Execute a query
result = schema.execute("""
    query {
        products {
            id
            name
            price
        }
    }
""")
```

### Multi-Schema Setup

```python
from rail_django import SchemaBuilder

# Public API (limited)
public_builder = SchemaBuilder(schema_name="public")
public_schema = public_builder.get_schema()

# Admin API (full access)
admin_builder = SchemaBuilder(schema_name="admin")
admin_schema = admin_builder.get_schema()
```

### Custom Settings

```python
from rail_django import SchemaBuilder
from rail_django.core.settings import SchemaSettings

custom_settings = SchemaSettings(
    excluded_apps=["legacy_app"],
    enable_pagination=True,
    auto_camelcase=True
)

builder = SchemaBuilder(
    schema_name="custom",
    settings=custom_settings
)
schema = builder.get_schema()
```

### With Registry

```python
from rail_django import SchemaBuilder
from rail_django.core.registry import schema_registry

# Register schemas
schema_registry.register_schema(
    name="ecommerce",
    apps=["products", "orders", "customers"],
    settings={
        "mutation_settings": {
            "enable_bulk_operations": True
        }
    }
)

# Build schema using registry
builder = SchemaBuilder(
    schema_name="ecommerce",
    registry=schema_registry
)
schema = builder.get_schema()
```

## Performance Considerations

1. **Lazy Loading**: Generators are created on first access, not at initialization
2. **Schema Caching**: Built schema is cached until `clear_schema()` or `rebuild_schema()`
3. **Model Filtering**: Models are filtered early to avoid unnecessary processing
4. **Settings Refresh**: Disabled when settings are explicitly provided

## Related Modules

- [Schema Registry](./schema-registry.md) - Multi-schema management
- [Type Generator](../generators/type-generator.md) - GraphQL type creation
- [Query Generator](../generators/query-generator.md) - Query field generation
- [Mutation Generator](../generators/mutation-generator.md) - Mutation generation
- [Settings System](./settings.md) - Configuration reference
