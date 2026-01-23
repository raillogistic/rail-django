# Schema Registry

> **Module Path:** `rail_django.core.registry.registry`

The SchemaRegistry is the central management system for multiple GraphQL schemas. It handles schema registration, discovery, model mapping, and builder caching.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       SchemaRegistry                            │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Registered Schemas                     │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │  │
│  │  │  "default"  │  │   "admin"   │  │   "auth"    │      │  │
│  │  │ SchemaInfo  │  │ SchemaInfo  │  │ SchemaInfo  │      │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Discovery Hooks                          │  │
│  │  • App scanning (schemas.py, graphql_schema.py)          │  │
│  │  • Settings fallback (RAIL_DJANGO_GRAPHQL_SCHEMAS)       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Builder Cache                            │  │
│  │  { "default": SchemaBuilder, "admin": SchemaBuilder }    │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Class Reference

### SchemaRegistry

```python
from rail_django.core.registry import schema_registry

# Register a new schema
schema_info = schema_registry.register_schema(
    name="store",
    description="E-commerce API",
    version="2.0.0",
    apps=["products", "orders"],
    settings={
        "schema_settings": {
            "authentication_required": True
        }
    }
)

# Get schema info
info = schema_registry.get_schema("store")

# List all schemas
all_schemas = schema_registry.list_schemas()
```

### SchemaInfo

Data class holding schema configuration:

```python
@dataclass
class SchemaInfo:
    name: str                           # Schema identifier
    description: str = ""               # Human-readable description
    version: str = "1.0.0"             # Schema version
    apps: list[str] = field(default_factory=list)      # App labels to include
    models: list[str] = field(default_factory=list)    # Specific models to include
    exclude_models: list[str] = field(default_factory=list)  # Models to exclude
    settings: dict[str, Any] = field(default_factory=dict)   # Schema settings
    schema_class: Optional[type] = None  # Custom schema class
    auto_discover: bool = True           # Auto-discover models
    enabled: bool = True                 # Whether schema is active
```

## Registration API

### register_schema()

Register a new or update an existing schema:

```python
schema_info = schema_registry.register_schema(
    name="api",
    description="Main API for frontend",
    version="1.0.0",
    apps=["users", "products", "orders"],
    models=None,  # Include all models from apps
    exclude_models=["users.PasswordResetToken"],
    settings={
        "schema_settings": {
            "enable_introspection": True,
            "authentication_required": True
        },
        "query_settings": {
            "default_page_size": 25
        },
        "mutation_settings": {
            "enable_bulk_operations": True
        }
    },
    auto_discover=True,
    enabled=True
)
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Required | Unique schema identifier |
| `description` | `str` | `""` | Human-readable description |
| `version` | `str` | `"1.0.0"` | Schema version string |
| `apps` | `list[str]` | `None` | App labels to include |
| `models` | `list[str]` | `None` | Specific models (e.g., `["app.Model"]`) |
| `exclude_models` | `list[str]` | `None` | Models to exclude |
| `settings` | `dict` | `None` | Schema-specific settings |
| `schema_class` | `type` | `None` | Custom schema class |
| `auto_discover` | `bool` | `True` | Enable model auto-discovery |
| `enabled` | `bool` | `True` | Whether schema is active |

### unregister_schema()

Remove a schema from the registry:

```python
success = schema_registry.unregister_schema("temporary")
if success:
    print("Schema removed")
```

## Query API

### get_schema()

Get schema information by name:

```python
schema_info = schema_registry.get_schema("default")
if schema_info:
    print(f"Version: {schema_info.version}")
    print(f"Apps: {schema_info.apps}")
```

### list_schemas()

List all registered schemas:

```python
# All schemas
all_schemas = schema_registry.list_schemas()

# Only enabled schemas
enabled = schema_registry.list_schemas(enabled_only=True)

for schema in enabled:
    print(f"{schema.name}: {schema.description}")
```

### get_schema_names()

Get list of schema names:

```python
names = schema_registry.get_schema_names()
# ['default', 'admin', 'auth']

enabled_names = schema_registry.get_schema_names(enabled_only=True)
```

### schema_exists()

Check if a schema exists:

```python
if schema_registry.schema_exists("admin"):
    print("Admin schema is registered")
```

## Model Discovery

### get_models_for_schema()

Get Django models for a specific schema:

```python
models = schema_registry.get_models_for_schema("store")

for model in models:
    print(f"{model._meta.app_label}.{model.__name__}")
```

The method:
1. Collects models from registered `apps`
2. Filters by `models` list if specified
3. Excludes models in `exclude_models`

### validate_schema()

Validate schema configuration:

```python
result = schema_registry.validate_schema("store")

print(f"Valid: {result['valid']}")
print(f"Errors: {result['errors']}")
print(f"Warnings: {result['warnings']}")
print(f"Model count: {result['model_count']}")
```

## Schema Management

### enable_schema() / disable_schema()

Enable or disable a schema at runtime:

```python
# Disable admin schema
schema_registry.disable_schema("admin")

# Enable later
schema_registry.enable_schema("admin")
```

### clear()

Clear all schemas from the registry:

```python
schema_registry.clear()
# All schemas removed, caches cleared
```

## Builder Integration

### get_schema_builder()

Get or create a SchemaBuilder for a schema:

```python
builder = schema_registry.get_schema_builder("default")
schema = builder.get_schema()
```

### get_cached_schema_builder()

Get cached builder without creating new one:

```python
builder = schema_registry.get_cached_schema_builder("default")
if builder is None:
    print("Builder not yet created")
```

### get_schema_instance()

Get the built Graphene schema:

```python
schema = schema_registry.get_schema_instance("default")
result = schema.execute("query { products { id } }")
```

## Discovery System

### Auto-Discovery

The registry can auto-discover schemas from installed apps:

```python
# Scan apps for schema files
schema_registry.discover_schemas()

# Alternative: auto-discover all
count = schema_registry.auto_discover_schemas()
print(f"Discovered {count} schemas")
```

Discovery looks for these files in each app:
1. `schemas.py`
2. `graphql_schema.py`
3. `schema.py`
4. `graphql/schema.py`

### Discovery Hooks

Add custom discovery logic:

```python
def my_discovery_hook(registry, app_config):
    """Custom schema discovery for an app."""
    if hasattr(app_config, 'graphql_schemas'):
        for schema_config in app_config.graphql_schemas:
            registry.register_schema(**schema_config)

schema_registry.add_discovery_hook(my_discovery_hook)
```

## Registration Hooks

### Pre-Registration Hooks

Modify schema configuration before registration:

```python
def enforce_security(registry, name, **kwargs):
    """Ensure all schemas require authentication."""
    settings = kwargs.get('settings', {})
    schema_settings = settings.get('schema_settings', {})
    schema_settings['authentication_required'] = True
    settings['schema_settings'] = schema_settings
    return {'settings': settings}

schema_registry.add_pre_registration_hook(enforce_security)
```

### Post-Registration Hooks

React to schema registration:

```python
def log_registration(registry, schema_info):
    """Log when schemas are registered."""
    print(f"Schema registered: {schema_info.name} v{schema_info.version}")

schema_registry.add_post_registration_hook(log_registration)
```

## GraphiQL Defaults

The registry applies special defaults for the "graphiql" schema:

```python
# When DEBUG=True:
# - enable_graphiql: True
# - enable_introspection: True
# - authentication_required: False

# When DEBUG=False:
# - enable_graphiql: False
# - enable_introspection: False
# - authentication_required: True
```

## Thread Safety

The registry uses threading locks for safe concurrent access:

```python
def register_schema(self, name, ...):
    with self._lock:
        # Thread-safe registration
        ...
```

## Usage Examples

### Multi-Schema API

```python
from rail_django.core.registry import schema_registry

# Public API - limited access
schema_registry.register_schema(
    name="public",
    description="Public API for anonymous users",
    apps=["products"],
    settings={
        "schema_settings": {
            "authentication_required": False,
            "enable_graphiql": False,
            "query_field_allowlist": ["products", "product", "categories"]
        },
        "mutation_settings": {
            "enable_create": False,
            "enable_update": False,
            "enable_delete": False
        }
    }
)

# Authenticated API - full access
schema_registry.register_schema(
    name="api",
    description="Authenticated API for logged-in users",
    apps=["products", "orders", "customers"],
    settings={
        "schema_settings": {
            "authentication_required": True
        }
    }
)

# Admin API - all features
schema_registry.register_schema(
    name="admin",
    description="Admin API with bulk operations",
    apps=["products", "orders", "customers", "analytics"],
    settings={
        "mutation_settings": {
            "enable_bulk_operations": True,
            "generate_bulk": True
        }
    }
)
```

### Register from App Config

```python
# myapp/apps.py
from django.apps import AppConfig

class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        from rail_django.core.registry import schema_registry

        schema_registry.register_schema(
            name="myapp",
            description="MyApp GraphQL API",
            apps=[self.name],
            version="1.0.0"
        )
```

### Register from schemas.py

```python
# myapp/schemas.py
def register_schema(registry):
    """Called during auto-discovery."""
    registry.register_schema(
        name="myapp",
        apps=["myapp"],
        settings={
            "query_settings": {
                "default_page_size": 50
            }
        }
    )
```

### Dynamic Schema Management

```python
from rail_django.core.registry import schema_registry

def create_tenant_schema(tenant_id):
    """Create a schema for a specific tenant."""
    schema_registry.register_schema(
        name=f"tenant_{tenant_id}",
        description=f"API for tenant {tenant_id}",
        apps=["core", "billing"],
        settings={
            "multitenancy_settings": {
                "tenant_id": tenant_id
            }
        }
    )

def remove_tenant_schema(tenant_id):
    """Remove a tenant's schema."""
    schema_registry.unregister_schema(f"tenant_{tenant_id}")
```

## Global Registry Access

The global registry is available as a singleton:

```python
from rail_django.core.registry import schema_registry

# This is the global registry used by the framework
schema_registry.register_schema(...)
```

For testing, you can create a local registry:

```python
from rail_django.core.registry import SchemaRegistry

local_registry = SchemaRegistry()
local_registry.register_schema(name="test", apps=["testapp"])
```

## Configuration via Settings

Schemas can also be configured in Django settings:

```python
# settings.py
RAIL_DJANGO_GRAPHQL_SCHEMAS = {
    "default": {
        "apps": ["products", "orders"],
        "schema_settings": {
            "authentication_required": True
        }
    },
    "admin": {
        "apps": ["products", "orders", "analytics"],
        "mutation_settings": {
            "enable_bulk_operations": True
        }
    }
}
```

These are automatically registered during framework initialization.

## Related Modules

- [Schema Builder](./schema-builder.md) - Builds schemas from registry info
- [Settings System](./settings.md) - Configuration hierarchy
- [Discovery System](./discovery.md) - Auto-discovery details
