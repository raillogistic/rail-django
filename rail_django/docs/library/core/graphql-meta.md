# GraphQLMeta reference

> **Module path:** `rail_django.core.meta`

`GraphQLMeta` is the per-model configuration helper used by Rail Django
generators. It controls field exposure, filtering, ordering, operation guards,
relation operation policy, and metadata exported to clients.

## Define model config

Define an inner class named `GraphQLMeta` or `GraphqlMeta` on your model.

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig


class Product(models.Model):
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=24)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey("Category", on_delete=models.CASCADE)

    class GraphqlMeta(GraphQLMetaConfig):
        fields = GraphQLMetaConfig.Fields(
            exclude=["internal_notes"],
            read_only=["created_at"],
        )
        filtering = GraphQLMetaConfig.Filtering(
            quick=["name"],
            fields={
                "status": GraphQLMetaConfig.FilterField(lookups=["eq", "in"]),
                "price": GraphQLMetaConfig.FilterField(
                    lookups=["eq", "gt", "lt", "between"]
                ),
            },
        )
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "price", "created_at"],
            default=["-created_at"],
        )
```

## Available config classes

Use these aliases from `GraphQLMeta` inside your inner meta class.

| Alias | Dataclass | Purpose |
|---|---|---|
| `FilterField` | `FilterFieldConfig` | Field filter operators and choices |
| `Filtering` | `FilteringConfig` | Quick filter and filter map |
| `Fields` | `FieldExposureConfig` | `include`, `exclude`, `read_only`, `write_only` |
| `Ordering` | `OrderingConfig` | Allowed and default ordering |
| `Resolvers` | `ResolverConfig` | Custom query, mutation, and field resolvers |
| `Role` | `RoleConfig` | Role declarations |
| `OperationGuard` | `OperationGuardConfig` | Operation-level guard rules |
| `FieldGuard` | `FieldGuardConfig` | Field-level masking and access rules |
| `AccessControl` | `AccessControlConfig` | Roles, operations, and field guards |
| `Classification` | `ClassificationConfig` | Model and field tags |
| `Pipeline` | `PipelineConfig` | Mutation pipeline customization |
| `RelationOperation` | `RelationOperationConfig` | Per-relation operation toggle |
| `FieldRelation` | `FieldRelationConfig` | Relation style and operation policy |

## Main sections on inner meta

The generated `GraphQLMeta` object reads a fixed set of attributes from your
inner class.

- `fields`: field exposure settings.
- `filtering`: quick filter and per-field filters.
- `ordering`: ordering allowlist and defaults.
- `resolvers`: custom resolver references.
- `access`: operation guards, roles, and field guards.
- `classifications`: data classification tags.
- `pipeline`: per-model mutation pipeline overrides.
- `relations`: per-relation operation policy used by nested mutations.
- `custom_metadata`, `field_metadata`, `field_groups`: metadata passed through
  to schema consumers.
- `tenant_field`: optional tenant path used by multitenancy integrations.

## Relation operation policy

Relation policy is read from `relations` and exposed with helper methods.

```python
class GraphqlMeta(GraphQLMetaConfig):
    relations = {
        "items": GraphQLMetaConfig.FieldRelation(
            style="unified",
            create=GraphQLMetaConfig.RelationOperation(enabled=False),
            update=GraphQLMetaConfig.RelationOperation(enabled=False),
        )
    }
```

When `style="id_only"`, nested `create` and `update` are treated as disabled.

## Public helper methods

Use `get_model_graphql_meta(model)` to get a cached helper instance, then call
its API methods.

```python
from rail_django.core.meta import get_model_graphql_meta

meta = get_model_graphql_meta(Product)
```

Important methods:

- `ensure_operation_access(operation, info, instance=None)`: enforce guards and
  raise `GraphQLError` when denied.
- `describe_operation_guard(operation, user=None, instance=None)`: evaluate a
  guard without raising.
- `should_expose_field(field_name, for_input=False)`: check field visibility.
- `apply_quick_filter(queryset, search_value)`: apply quick search fields with
  configured lookup.
- `get_custom_resolver(...)`, `apply_custom_resolver(...)`: custom resolver
  access and execution.
- `get_custom_filter(...)`, `get_custom_filters()`,
  `apply_custom_filter(...)`: custom filter access and execution.
- `get_filter_fields()`: return normalized filter lookup map.
- `get_ordering_fields()`: return allowed/default ordering fields.
- `get_relation_config(field_name)`: return relation policy for one field.
- `is_operation_allowed(field_name, operation)`: check relation operation
  enablement.

## Resolution and caching behavior

`get_model_graphql_meta(model)` creates one cached helper per model on
`model._graphql_meta_instance`. Meta source resolution is:

1. `model.GraphQLMeta` if present.
2. `model.GraphqlMeta` if present.
3. JSON-backed config loader fallback (`core.meta.json_loader`).

## Related pages

- [Type generator](../generators/type-generator.md)
- [Query generator](../generators/query-generator.md)
- [Mutation generator](../generators/mutation-generator.md)
