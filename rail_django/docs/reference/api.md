# Public API reference

This page summarizes the stable import paths that Rail Django exposes for
framework setup, schema registration, security, and plugin extensions.

## Form API

GraphQL reference for the Form API extension.

See `reference/form-api.md`.

## Schema Registry

Use the schema registry helpers when you need to register schemas or mutations
explicitly instead of relying on app discovery.

### `rail_django.core.registry.register_schema`

Registers a schema module or class manually.

```python
from rail_django.core.registry import register_schema

register_schema(name="default", description="My API")
```

### `rail_django.core.registry.register_mutation`

Registers a custom mutation class to the root Mutation.

```python
from rail_django.core.registry import register_mutation

register_mutation(MyMutation, name="custom_mutation", schema_name="default")
```

## Core package

Use the top-level package or `rail_django.core` for configuration and schema
builder entry points.

### `rail_django.ConfigLoader`

Loads merged framework settings without requiring you to import internal
configuration modules directly.

```python
from rail_django import ConfigLoader

config = ConfigLoader.get_rail_django_settings()
```

### `rail_django.SchemaBuilder`

Builds a GraphQL schema for a registered schema name.

```python
from rail_django import SchemaBuilder

builder = SchemaBuilder(schema_name="default")
schema = builder.get_schema()
```

## Security

Use the security package when you need explicit authorization or input
validation hooks inside custom resolvers and mutations.

### `rail_django.security.rbac.require_role`

Decorator to enforce role requirements on a resolver.

```python
from rail_django.security.rbac import require_role

@require_role("admin")
def resolve_field(root, info): ...
```

### `rail_django.security.validation.validate_input`

Decorator to validate and sanitize input arguments.

```python
from rail_django.security.validation import validate_input

@validate_input()
def resolve_mutation(root, info, input): ...
```

## Plugins

Use the plugins package when you need to extend schema discovery, schema
building, or GraphQL execution with framework-level hooks.

### `rail_django.plugins.BasePlugin`

Base class for framework plugins.

```python
from rail_django.plugins import BasePlugin

class AuditPlugin(BasePlugin):
    def get_name(self) -> str:
        return "audit-plugin"
```

### `rail_django.plugins.ExecutionHookResult`

Short-circuits resolver or operation execution when a plugin handles the
request.

```python
from rail_django.plugins import ExecutionHookResult

result = ExecutionHookResult(handled=True, result=None)
```
