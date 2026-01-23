# Unified Input with Operation Semantics - Implementation Plan

## Overview

Replace the current "dual field" pattern (`<field>` + `nested_<field>`) with "Unified Input with Operation Semantics" where a single relation field accepts explicit operation keys (`connect`, `create`, `update`, `disconnect`, `set`).

**Breaking Change:** This is a non-backward-compatible migration. All existing mutations using `nested_<field>` pattern will need to be updated.

### Current vs Target API

**Current (Dual Field) - TO BE REMOVED:**
```graphql
mutation {
  createPost(input: {
    title: "Hello"
    author: "123"                    # OR
    nestedAuthor: { name: "John" }   # Can't mix intuitively
  }) { ... }
}
```

**Target (Unified) - NEW:**
```graphql
mutation {
  createPost(input: {
    title: "Hello"
    author: { connect: "123" }              # Clear intent
    # OR
    author: { create: { name: "John" } }    # Inline create
    tags: [
      { connect: "1" },
      { create: { name: "GraphQL" } }       # Mix operations
    ]
  }) { ... }
}
```

---

## Phase 1: Foundation (New Types Infrastructure)

### New Files to Create

| File | Purpose |
|------|---------|
| `rail_django/generators/types/relations.py` | `RelationInputTypeGenerator` - generates `<Model>RelationInput` types |
| `rail_django/generators/types/relation_config.py` | Configuration dataclasses for per-field operation control |

### Key Implementation: `RelationInputTypeGenerator`

```python
class RelationInputTypeGenerator:
    def generate_relation_input_type(
        self,
        related_model: Type[Model],
        relation_type: str,  # "fk", "o2o", "m2m", "reverse"
        parent_model: Optional[Type[Model]] = None,
        depth: int = 0,
    ) -> Type[graphene.InputObjectType]:
        """Generate AuthorRelationInput with connect/create/update/disconnect keys."""
```

**Lazy Type Resolution:** Use `graphene.InputField(lambda: SomeType)` to handle circular references without infinite recursion.

### Files to Modify

| File | Changes |
|------|---------|
| `rail_django/core/settings/mutation_settings.py` | Add `relation_max_nesting_depth`, remove `nested_field_config` |
| `rail_django/defaults.py` | Update default values |

---

## Phase 2: Input Generation Replacement

### File: `rail_django/generators/types/inputs.py`

**Replace dual-field generation with unified inputs:**

1. **Remove** dual field generation code (lines 133-204)
2. **Replace** with unified relation input generation:

```python
# For each relationship field, generate single unified field
for field_name, rel_info in relationships.items():
    relation_input = self._relation_generator.generate_relation_input_type(
        related_model=rel_info.related_model,
        relation_type=self._get_relation_type(rel_info),
        parent_model=model,
    )
    input_fields[field_name] = graphene.InputField(relation_input, required=is_required)
```

3. **Remove** `_get_or_create_nested_input_type()` function (lines 229-310) - replaced by `RelationInputTypeGenerator`

---

## Phase 3: Pipeline Replacement

### File: `rail_django/generators/pipeline/steps/normalization.py`

**Remove `DualFieldProcessingStep`** and replace with:

```python
class RelationOperationProcessingStep(MutationStep):
    """Processes relation operation inputs (connect/create/update/disconnect/set)."""
    order = 45

    def execute(self, ctx: MutationContext) -> MutationContext:
        ctx.input_data = self._process_relation_operations(ctx.input_data, ctx.model)
        return ctx
```

**Validation Rules:**
- Exactly one operation per singular relation (FK/O2O)
- `set` cannot combine with `connect`/`disconnect`
- `disconnect`/`set` only valid for M2M/reverse

### Files to Modify

| File | Changes |
|------|---------|
| `rail_django/generators/pipeline/builder.py` | Replace `DualFieldProcessingStep` with `RelationOperationProcessingStep` |
| `rail_django/generators/pipeline/steps/validation.py` | Update validation for operation format |
| `rail_django/generators/pipeline/utils.py` | Remove `process_dual_fields()` function |

---

## Phase 4: Handler Refactoring

### New File: `rail_django/generators/nested/operations.py`

```python
@dataclass
class RelationOperation:
    operation: str  # "connect", "create", "update", "disconnect", "set"
    data: Any
    field_name: str
    related_model: Type[Model]

class RelationOperationProcessor:
    def process_relation(self, instance, field_name, operations_data):
        """Process all operations for a relation field uniformly."""
```

**Operation Processing Order:** `set` → `disconnect` → `connect` → `create` → `update`

### Files to Modify

| File | Changes |
|------|---------|
| `rail_django/generators/nested/handler.py` | Replace `_process_nested_fields()` with `process_relation_input()` |
| `rail_django/generators/nested/create.py` | Use `RelationOperationProcessor` in `handle_nested_create()` |
| `rail_django/generators/nested/update.py` | Use `RelationOperationProcessor` in `handle_nested_update()` |

---

## Phase 5: Configuration & GraphQLMeta

### File: `rail_django/core/meta/graphql_meta.py`

**Add per-field relation configuration:**

```python
class Post(models.Model):
    class GraphqlMeta(GraphQLMeta):
        relations = {
            "author": GraphQLMeta.FieldRelation(
                style="unified",
                connect=GraphQLMeta.RelationOperation(enabled=True),
                create=GraphQLMeta.RelationOperation(
                    enabled=True,
                    require_permission="can_create_author",
                ),
                update=GraphQLMeta.RelationOperation(enabled=False),
            ),
        }
```

### Files to Modify

| File | Changes |
|------|---------|
| `rail_django/core/meta/config.py` | Add `RelationOperationConfig`, `FieldRelationConfig` dataclasses |
| `rail_django/core/meta/graphql_meta.py` | Add `get_relation_config()`, `is_operation_allowed()` |

---

## Phase 6: Testing & Documentation

### New Test Files

| File | Coverage |
|------|----------|
| `rail_django/tests/unit/test_relation_input_types.py` | RelationInputTypeGenerator, lazy types, circular refs |
| `rail_django/tests/unit/test_relation_operations.py` | Pipeline step, operation extraction, validation |
| `rail_django/tests/integration/test_unified_mutations.py` | Full mutation flow with unified inputs |

### Documentation Updates

| File | Changes |
|------|---------|
| `docs/core/mutations.md` | Add "Unified Relation Inputs" section |
| `docs/reference/configuration.md` | Document new settings |
| `docs/guides/migration-unified-inputs.md` | **New** - Migration guide |

---

## Critical Files Summary

| Priority | File | Phase |
|----------|------|-------|
| 1 | `rail_django/generators/types/relations.py` (new) | 1 |
| 2 | `rail_django/core/settings/mutation_settings.py` | 1 |
| 3 | `rail_django/generators/types/inputs.py` | 2 |
| 4 | `rail_django/generators/pipeline/steps/normalization.py` | 3 |
| 5 | `rail_django/generators/nested/operations.py` (new) | 4 |
| 6 | `rail_django/generators/nested/handler.py` | 4 |
| 7 | `rail_django/core/meta/graphql_meta.py` | 5 |

---

## Verification Plan

### After Each Phase

```bash
# Run unit tests
pytest rail_django/tests/unit/ -v

# Run integration tests
pytest rail_django/tests/integration/ -v

# Check formatting
python -m black --check rail_django/
```

### End-to-End Verification

1. **Create test project:**
   ```bash
   rail-admin startproject test_unified
   cd test_unified
   ```

2. **Test mutations via GraphiQL:**
   ```graphql
   mutation {
     createPost(input: {
       title: "Test"
       author: { create: { name: "New Author" } }
       tags: [
         { connect: "1" },
         { create: { name: "New Tag" } }
       ]
     }) {
       post { id title author { name } tags { name } }
     }
   }
   ```

3. **Verify schema introspection** shows the new `<Model>RelationInput` types with operation keys

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Circular reference infinite loops | Lazy type resolution + max depth limit (default: 3) |
| Schema conflicts | Separate type registry for relation inputs |
| Transaction integrity | All operations in single atomic transaction |
| Client migration | Clear migration guide in docs; schema introspection shows new structure |

---

## Implementation Order

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6
```

Sequential implementation recommended since this is a breaking change.
