# Plugin System Guide

This guide explains how to build and register Rail Django plugins against the
current plugin API. Use these hooks when you need framework-level behavior
around schema discovery, schema building, or GraphQL execution.

Rail Django features a powerful plugin system that lets you hook into various stages of the framework's lifecycle, from schema discovery and building to query execution and field resolution.

## Overview

Plugins are classes that inherit from `rail_django.plugins.BasePlugin`. They
are registered in your Django settings and are executed by the `PluginManager`.

Plugins can:
- Modify the schema build context.
- Intercept and modify schema generation.
- Execute logic before/after GraphQL operations.
- Intercept field resolution for security or monitoring.

## Creating a Plugin

To create a plugin, subclass `BasePlugin` and implement the hooks you need.

```python
# my_app/plugins.py
from rail_django.plugins import BasePlugin, ExecutionHookResult

class MyCustomPlugin(BasePlugin):
    """
    A plugin to log specific sensitive field access.
    """

    def get_name(self) -> str:
        return "my-custom-plugin"

    def pre_schema_build(self, schema_name, builder, context):
        # Called before the schema is built
        print(f"Building schema: {schema_name}")
        return context

    def before_resolve(self, schema_name, info, root, kwargs, context):
        # Called before every field resolution
        if info.field_name == "sensitiveData":
            user = context.get('user')
            if not user or not user.is_staff:
                # Block access and return None
                return ExecutionHookResult(handled=True, result=None)

        # Continue with normal resolution
        return ExecutionHookResult(handled=False)
```

## Registering Plugins

Register your plugin in `settings.py` under `GRAPHQL_SCHEMA_PLUGINS`.

```python
# settings.py

GRAPHQL_SCHEMA_PLUGINS = {
    'my_app.plugins.MyCustomPlugin': {
        'enabled': True,
        'custom_option': 'value',
    },
    # Built-in plugins can also be configured here
    'rail_django.extensions.observability.ObservabilityPlugin': {
        'enabled': True,
    }
}
```

## Available Hooks

### Registry hooks

Use registry hooks to influence schema registration and discovery.

- `pre_registration_hook(registry, schema_name, **kwargs)`: Called before a
  schema is registered. Return a dictionary to override registration
  parameters.
- `post_registration_hook(registry, schema_info)`: Called after a schema is
  registered.
- `discovery_hook(registry)`: Called during schema discovery after app modules
  have been scanned.

### Schema build hooks

Use schema build hooks to add data to the build context or react after a
Graphene schema is created.

- `pre_schema_build(schema_name, builder, context)`: Called before the schema
  is constructed. Return a dictionary to add values to the build context.
- `post_schema_build(schema_name, builder, schema, context)`: Called after the
  Graphene schema is finalized.

### Execution hooks

Use execution hooks to observe or intercept GraphQL operations and resolver
execution.

- `before_operation(schema_name, operation_type, operation_name, info,
  context)`: Called before a root GraphQL operation runs.
- `after_operation(schema_name, operation_type, operation_name, info, result,
  error, context)`: Called after a root GraphQL operation finishes.
- `before_resolve(schema_name, info, root, kwargs, context)`: Called before a
  field resolver runs. Return `ExecutionHookResult(handled=True, result=...)`
  to bypass the resolver.
- `after_resolve(schema_name, info, root, kwargs, result, error, context)`:
  Called after a field resolver returns or raises.

## ExecutionHookResult

For execution hooks like `before_resolve`, return an
`ExecutionHookResult` when you need to stop normal processing.

```python
class ExecutionHookResult:
    def __init__(self, handled: bool = False, result: Any = None):
        self.handled = handled  # If True, stops further processing
        self.result = result    # The return value if handled=True
```

## Example: Request Timing Plugin

Here is a simple plugin that measures the time taken for the entire operation.

```python
import time
from rail_django.plugins import BasePlugin

class TimingPlugin(BasePlugin):
    def get_name(self) -> str:
        return "timing-plugin"

    def before_operation(self, schema_name, operation_type, operation_name, info, context):
        context['start_time'] = time.time()

    def after_operation(self, schema_name, operation_type, operation_name, info, result, error, context):
        duration = time.time() - context.get('start_time', time.time())
        print(f"Operation took {duration:.4f}s")
```
