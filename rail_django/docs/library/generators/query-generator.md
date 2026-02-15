# Query generator internals

> **Module path:** `rail_django.generators.queries.generator`

`QueryGenerator` builds GraphQL query fields for model retrieval, filtering,
ordering, pagination, and grouping. It delegates concrete field creation to the
query helper modules and applies model policy from `GraphQLMeta`.

## Constructor and dependencies

Create a query generator with a `TypeGenerator`.

```python
from rail_django.generators.types import TypeGenerator
from rail_django.generators.queries import QueryGenerator

type_gen = TypeGenerator(schema_name="default")
query_gen = QueryGenerator(type_gen, schema_name="default")
```

Constructor arguments:

- `type_generator: TypeGenerator`
- `settings: QueryGeneratorSettings | None`
- `schema_name: str = "default"`

Core runtime dependencies include the authorization manager, query optimizer,
performance monitor, and the advanced filter generator.

## Public methods

Use these methods to generate query fields.

| Method | Purpose |
|---|---|
| `generate_single_query(model, manager_name="objects")` | Single record query by `id` |
| `generate_list_query(model, manager_name="objects")` | List query with filters, ordering, and offset/limit |
| `generate_paginated_query(...)` | Page-based query with `page_info` metadata |
| `generate_grouping_query(model, manager_name="objects")` | Group-by counts (`key`, `label`, `count`) |
| `add_filtering_support(query, model)` | Adds filter arguments to an existing field |
| `generate_introspection_queries()` | Returns `{}` (metadata extension owns this now) |

## Query argument model

List and paginated queries are built from shared argument helpers. Depending on
mode and enabled features, generated fields can expose:

- `where`
- `presets`
- `savedFilter`
- `include`
- `quick`
- `order_by`
- `distinct_on`
- `offset` and `limit` (list mode)
- `page` and `per_page` (paginated mode)
- `skip_count` (paginated mode)
- filterset-derived arguments (when a filter class is generated)

## Single query behavior

Single queries enforce permissions, tenant scope, and operation guards before
returning the object.

- Input is `id` (required).
- Missing rows return `None`.
- Field-level masking is applied to the returned instance.

## List query behavior

List queries run through a filter and ordering pipeline.

- Enforces model permission and `GraphQLMeta` operation access (`list`).
- Applies tenant scoping.
- Applies optimizer hints.
- Applies nested `where` filters, presets, saved filters, and quick search.
- Applies ordering, including optional property-based ordering fallback.
- Applies offset/limit pagination when enabled.
- Masks protected fields on returned rows.

If `use_relay=True` and relay dependencies are present, the generator can return
`DjangoFilterConnectionField` instead of a plain list field.

## Paginated query behavior

Paginated queries return a dynamic connection-like object with:

- `items`
- `page_info` (`total_count`, `page_count`, `current_page`, `per_page`,
  `has_next_page`, `has_previous_page`)

With `skip_count=True`, expensive total-count calculation is skipped and
`total_count`/`page_count` are unset.

## Grouping query behavior

Grouping queries provide lightweight aggregated buckets.

- Required argument: `group_by`
- Optional arguments: `order_by`, `limit`, filters, and nested `where`
- Return shape: list of bucket objects with `key`, `label`, `count`

Grouping rejects unknown field paths and many-to-many group paths.

## Manager utilities

The generator also exposes manager inspection helpers:

- `get_manager_queryset_model(model, manager_name)`
- `is_history_related_manager(model, manager_name)`

These are used by higher-level schema assembly to safely handle custom managers
and history managers.

## Security and multitenancy model

Query enforcement happens in layers.

- Model permission checks use `QueryGeneratorSettings.model_permission_codename`
  (default `view`) when `require_model_permissions=True`.
- If an operation guard exists for the same operation in `GraphQLMeta`, the
  direct model permission check is skipped in favor of guard evaluation.
- Tenant scoping and tenant instance access checks run through the multitenancy
  extension hooks when available.
- Field masking is applied for non-superusers.

## Settings reference

`QueryGeneratorSettings` fields:

- `generate_filters`
- `generate_ordering`
- `generate_pagination`
- `enable_pagination`
- `enable_ordering`
- `use_relay`
- `default_page_size`
- `max_page_size`
- `max_grouping_buckets`
- `max_property_ordering_results`
- `property_ordering_warn_on_cap`
- `additional_lookup_fields`
- `require_model_permissions`
- `model_permission_codename`

## Usage example

```python
import graphene
from rail_django.generators.types import TypeGenerator
from rail_django.generators.queries import QueryGenerator
from myapp.models import Product

type_gen = TypeGenerator(schema_name="default")
query_gen = QueryGenerator(type_gen, schema_name="default")

class Query(graphene.ObjectType):
    product = query_gen.generate_single_query(Product)
    product_list = query_gen.generate_list_query(Product)
    product_page = query_gen.generate_paginated_query(Product)
    product_group = query_gen.generate_grouping_query(Product)
```

## Related pages

- [Type generator](./type-generator.md)
- [Mutation generator](./mutation-generator.md)
- [GraphQLMeta](../core/graphql-meta.md)
