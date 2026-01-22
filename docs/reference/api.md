# API Reference

## Schema Registry

Functions for manually registering schemas and mutations.

### `rail_django.core.registry.register_schema`

Registers a schema module or class manually.

```python
from rail_django.core.registry import register_schema

register_schema(schema_instance, schema_name="default")
```

### `rail_django.core.registry.register_mutation`

Registers a custom mutation class to the root Mutation.

```python
from rail_django.core.registry import register_mutation

register_mutation(MyMutation, schema_name="default")
```

## Security

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

## Utilities

### `rail_django.utils.get_model_graphql_meta`

Retrieves the `GraphQLMeta` instance for a given model.
