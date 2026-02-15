# Mutation generator internals

> **Module path:** `rail_django.generators.mutations.generator`

`MutationGenerator` builds GraphQL mutation classes for model CRUD, bulk
operations, and method-based actions. Create, update, and delete mutations use
a pipeline backend for consistent auth, validation, and auditing.

## Constructor and dependencies

Create a mutation generator from an existing `TypeGenerator`.

```python
from rail_django.generators.types import TypeGenerator
from rail_django.generators.mutations import MutationGenerator

type_gen = TypeGenerator(schema_name="default")
mutation_gen = MutationGenerator(type_gen, schema_name="default")
```

Constructor arguments:

- `type_generator: TypeGenerator`
- `settings: MutationGeneratorSettings | None`
- `schema_name: str = "default"`

On initialization, the generator wires authentication, authorization, input
validation, error handling, query optimization, nested operation handling, and
pipeline builder components.

## Public methods

These methods are the main mutation API.

| Method | Purpose |
|---|---|
| `generate_create_mutation(model)` | Create one row (pipeline factory) |
| `generate_update_mutation(model)` | Update one row by `id` (pipeline factory) |
| `generate_delete_mutation(model)` | Delete one row by `id` (pipeline factory) |
| `generate_bulk_create_mutation(model)` | Create many rows |
| `generate_bulk_update_mutation(model)` | Update many rows |
| `generate_bulk_delete_mutation(model)` | Delete many rows |
| `convert_method_to_mutation(...)` | Convert one model method to a mutation class |
| `generate_method_mutation(model, method_info)` | Build a method mutation from introspection metadata |
| `generate_all_mutations(model)` | Build full mutation field map for a model |

## CRUD mutation shape

Pipeline-generated CRUD mutations return a standardized payload model.

- Common fields: `ok`, `errors`
- CRUD object field: `object`

Argument model:

- Create: `input`
- Update: `id`, `input`
- Delete: `id`

Input types come from `TypeGenerator.generate_input_type(...)`.

## Bulk mutation shape

Bulk mutation classes are generated from `mutations/bulk.py`.

- Common fields: `ok`, `errors`, `objects`
- Bulk create args: `inputs: [CreateInput]`
- Bulk update args: `inputs: [{id, data}]`
- Bulk delete args: `ids: [ID]`

Bulk handlers enforce model permission checks, tenant scoping, and operation
access guards. They also normalize enum input values before persistence.

## Method mutation model

Rail Django supports two paths for method mutations.

1. `generate_method_mutation(model, method_info)`
: Uses introspector metadata and usually exposes `id` plus optional `input`.

2. `convert_method_to_mutation(model, method_name, ...)`
: Converts a method directly and exposes `id` plus method parameters as
  top-level args.

Both return payload fields `ok`, `result`, and `errors`.

## Pipeline model

Create, update, and delete pipelines are assembled by `PipelineBuilder`.

Default create pipeline order:

1. `AuthenticationStep`
2. `ModelPermissionStep`
3. `OperationGuardStep`
4. `InputSanitizationStep`
5. `EnumNormalizationStep`
6. `RelationOperationProcessingStep`
7. `ReadOnlyFieldFilterStep`
8. `CreatedByStep`
9. `TenantInjectionStep`
10. `InputValidationStep`
11. `NestedLimitValidationStep`
12. `NestedDataValidationStep`
13. `CreateExecutionStep`
14. `AuditStep`

Update and delete pipelines include `InstanceLookupStep` and operation-specific
execution steps.

## Permission and tenant enforcement

Mutation security follows generator settings and `GraphQLMeta` guards.

- Model permission checks are enabled when `require_model_permissions=True`.
- Permission codenames resolve via `model_permission_codenames`.
- Operation guards in `GraphQLMeta` override direct model-permission checks for
  the same operation.
- Tenant scoping is applied to lookup/query paths.
- Tenant input injection is applied for create/update payloads.

## generate_all_mutations behavior

`generate_all_mutations(model)` returns a dict of GraphQL fields ready to attach
to your mutation root.

Generation rules:

- CRUD fields are added for managed models when corresponding `enable_*` flags
  are true.
- Bulk fields are added only when bulk operations are enabled and inclusion and
  exclusion rules match.
- Method mutations are discovered via model introspection and added when
  method metadata marks them as mutation-capable.

## Settings reference

`MutationGeneratorSettings` fields:

- `generate_create`
- `generate_update`
- `generate_delete`
- `generate_bulk`
- `enable_create`
- `enable_update`
- `enable_delete`
- `enable_bulk_operations`
- `enable_method_mutations`
- `require_model_permissions`
- `model_permission_codenames`
- `bulk_batch_size`
- `bulk_include_models`
- `bulk_exclude_models`
- `required_update_fields`
- `enable_nested_relations`
- `relation_max_nesting_depth`
- `nested_relations_config`

## Usage example

```python
import graphene
from rail_django.generators.types import TypeGenerator
from rail_django.generators.mutations import MutationGenerator
from myapp.models import Product

type_gen = TypeGenerator(schema_name="default")
mutation_gen = MutationGenerator(type_gen, schema_name="default")

class Mutation(graphene.ObjectType):
    # Full set based on settings and model metadata
    locals().update(mutation_gen.generate_all_mutations(Product))
```

## Related pages

- [Type generator](./type-generator.md)
- [Query generator](./query-generator.md)
- [GraphQLMeta](../core/graphql-meta.md)
