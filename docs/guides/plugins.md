# Plugin System Guide

Rail Django features a powerful plugin system that allows you to hook into various stages of the framework's lifecycle, from schema discovery and building to query execution and field resolution.

## Overview

Plugins are classes that inherit from `rail_django.plugins.base.BasePlugin`. They are registered in your Django settings and are executed by the `PluginManager`.

Plugins can:
*   Modify the schema build context.
*   Intercept and modify schema generation.
*   Execute logic before/after GraphQL operations.
*   Intercept field resolution for security or monitoring.

## Creating a Plugin

To create a plugin, subclass `BasePlugin` and implement the hooks you need.

```python
# my_app/plugins.py
from rail_django.plugins.base import BasePlugin, ExecutionHookResult

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

### Registry Hooks

*   `pre_registration_hook(registry)`: Called before apps are scanned.
*   `discovery_hook(registry, app_name, module)`: Called when a schema module is discovered.
*   `post_registration_hook(registry)`: Called after all schemas are registered.

### Schema Build Hooks

*   `pre_schema_build(schema_name, builder, context)`: Called before the schema is constructed. Useful for modifying the build context.
*   `post_schema_build(schema_name, schema)`: Called after the Graphene schema is finalized.

### Execution Hooks

*   `before_operation(schema_name, document, context, variables)`: Called before a GraphQL query is executed.
*   `after_operation(schema_name, document, context, result, error)`: Called after execution completes.
*   `before_resolve(schema_name, info, root, kwargs, context)`: Called before a field resolver runs. Return `ExecutionHookResult(handled=True, result=...)` to bypass the resolver.
*   `after_resolve(schema_name, info, result, context)`: Called after a field resolver returns.

## ExecutionHookResult

For execution hooks like `before_resolve`, you must return an `ExecutionHookResult`.

```python
class ExecutionHookResult:
    def __init__(self, handled: bool = False, result: Any = None, error: Exception = None):
        self.handled = handled  # If True, stops further processing
        self.result = result    # The return value if handled=True
        self.error = error      # Exception to raise if handled=True
```

## Example: Request Timing Plugin

Here is a simple plugin that measures the time taken for the entire operation.

```python
import time
from rail_django.plugins.base import BasePlugin

class TimingPlugin(BasePlugin):
    def get_name(self) -> str:
        return "timing-plugin"

    def before_operation(self, schema_name, document, context, variables):
        context['start_time'] = time.time()

    def after_operation(self, schema_name, document, context, result, error):
        duration = time.time() - context.get('start_time', time.time())
        print(f"Operation took {duration:.4f}s")
```
