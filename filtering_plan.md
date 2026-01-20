# Rail-Django Advanced Filtering Implementation Plan

This document outlines the implementation plan for next-level filtering features in the Rail-Django GraphQL framework.

## Current State

The filtering system (`rail_django/generators/filter_inputs.py`) currently supports:

- Typed filter inputs (String, Int, Float, Boolean, Date, DateTime, ID, UUID, JSON, Count)
- Boolean operators (AND, OR, NOT)
- Relationship quantifiers (`_some`, `_every`, `_none`)
- Count filters (`_count`)
- Quick filter (multi-field search)
- Include filter (ID union)
- Temporal filters (today, this_week, this_month, etc.)
- Historical model support (django-simple-history)
- Performance analysis and optimization suggestions

---

## Phase 1: Aggregation Filters

**Priority:** P0 - High Impact
**Estimated Complexity:** Medium
**Files to modify:**

- `rail_django/generators/filter_inputs.py`
- `rail_django/tests/unit/test_nested_filters.py`
- `rail_django/tests/integration/test_nested_filters.py`
- `docs/guides/filtering.md`

**Status:** Completed

### Description

Allow filtering by aggregated values on related objects (SUM, AVG, MIN, MAX, COUNT with conditions).

### Implementation Steps

1. Create `AggregationFilterInput` types for each aggregate function (done)
2. Add `{relation}_agg` fields to WhereInput for reverse relations (done)
3. Implement `_build_aggregation_q()` method in `NestedFilterApplicator` (done)
4. Add required annotations to queryset before filtering (done)

### Delivered Work

- Added `AggregationFilterInput` and `{relation}_agg` fields for reverse and M2M relations.
- Implemented aggregation annotations and numeric filter handling in `NestedFilterApplicator`.
- Added unit and integration coverage for aggregation filters.
- Documented aggregation filter usage in the filtering guide.

### New Input Types

```python
class AggregationFilterInput(graphene.InputObjectType):
    """Filter by aggregated values on a numeric field."""
    field = graphene.String(required=True, description="Field to aggregate")
    sum = graphene.InputField(FloatFilterInput, description="Filter by SUM")
    avg = graphene.InputField(FloatFilterInput, description="Filter by AVG")
    min = graphene.InputField(FloatFilterInput, description="Filter by MIN")
    max = graphene.InputField(FloatFilterInput, description="Filter by MAX")
    count = graphene.InputField(IntFilterInput, description="Filter by COUNT")
```

### Usage Examples

```graphql
# Orders with total line items amount >= $1000
query {
  orders(where: { line_items_agg: { field: "amount", sum: { gte: 1000 } } }) {
    id
    customer_name
  }
}

# Products with average review rating >= 4.0
query {
  products(where: { reviews_agg: { field: "rating", avg: { gte: 4.0 } } }) {
    id
    name
  }
}

# Authors with more than 5 published books
query {
  authors(where: { books_agg: { field: "id", count: { gt: 5 } } }) {
    id
    name
  }
}

# Invoices where max line item price exceeds $500
query {
  invoices(
    where: { line_items_agg: { field: "unit_price", max: { gt: 500 } } }
  ) {
    id
    invoice_number
  }
}
```

### Backend Implementation

```python
def _build_aggregation_q(
    self,
    field_name: str,
    agg_filter: Dict[str, Any],
    model: Type[models.Model],
) -> Tuple[Q, Dict[str, Any]]:
    """Build Q object and annotations for aggregation filter."""
    annotations = {}
    q = Q()

    target_field = agg_filter.get("field", "id")

    if "sum" in agg_filter:
        ann_name = f"{field_name}_{target_field}_sum"
        annotations[ann_name] = Sum(f"{field_name}__{target_field}")
        q &= self._build_numeric_q(ann_name, agg_filter["sum"])

    if "avg" in agg_filter:
        ann_name = f"{field_name}_{target_field}_avg"
        annotations[ann_name] = Avg(f"{field_name}__{target_field}")
        q &= self._build_numeric_q(ann_name, agg_filter["avg"])

    # ... similar for min, max, count

    return q, annotations
```

---

## Phase 2: Full-Text Search

**Priority:** P0 - High Impact
**Estimated Complexity:** Low-Medium
**Files to modify:**

- `rail_django/generators/filter_inputs.py`
- `rail_django/core/settings.py` (add FTS settings)
- `rail_django/defaults.py`
- `rail_django/generators/queries_list.py`
- `rail_django/generators/queries_grouping.py`
- `rail_django/generators/queries_pagination.py`
- `rail_django/generators/subscriptions.py`
- `rail_django/tests/unit/test_nested_filters.py`
- `rail_django/tests/integration/test_nested_filters.py`
- `docs/guides/filtering.md`
- `docs/reference/configuration.md`

**Status:** Completed

### Description

Leverage database full-text search capabilities for efficient text searching with ranking.

### Implementation Steps

1. Create `FullTextSearchInput` type (done)
2. Add `search` field to WhereInput (done)
3. Implement `_build_fts_q()` method with Postgres `SearchVector`/`SearchQuery` (done)
4. Add fallback to `icontains` for non-Postgres databases (done)
5. Support search across multiple fields including relations (done)

### Delivered Work

- Added `FullTextSearchInput` and schema-gated `search` field generation.
- Implemented FTS query building with Postgres annotations and fallback behavior.
- Wired schema-scoped filtering settings and defaults for FTS configuration.
- Added unit/integration coverage and documentation updates.

### New Input Types

```python
class FullTextSearchInput(graphene.InputObjectType):
    """Full-text search configuration."""
    query = graphene.String(required=True, description="Search query")
    fields = graphene.List(
        graphene.NonNull(graphene.String),
        description="Fields to search (supports relations: 'author__name')"
    )
    config = graphene.String(
        default_value="english",
        description="Text search configuration (Postgres only)"
    )
    rank_threshold = graphene.Float(
        description="Minimum search rank (0.0-1.0)"
    )
    search_type = graphene.String(
        default_value="websearch",
        description="Search type: plain, phrase, websearch, raw"
    )
```

### Usage Examples

```graphql
# Simple full-text search
query {
  articles(
    where: {
      search: { query: "django graphql api", fields: ["title", "body"] }
    }
  ) {
    id
    title
    _search_rank # Optional: expose search rank
  }
}

# Search with minimum rank threshold
query {
  products(
    where: {
      search: {
        query: "wireless bluetooth headphones"
        fields: ["name", "description", "tags__name"]
        rank_threshold: 0.1
      }
    }
  ) {
    id
    name
  }
}

# Phrase search
query {
  documents(
    where: {
      search: {
        query: "machine learning"
        fields: ["content"]
        search_type: "phrase"
      }
    }
  ) {
    id
    title
  }
}

# Combined with other filters
query {
  products(
    where: {
      search: { query: "laptop", fields: ["name", "description"] }
      price: { lte: 1000 }
      category_rel: { name: { eq: "Electronics" } }
    }
  ) {
    id
    name
    price
  }
}
```

### Backend Implementation

```python
def _build_fts_q(
    self,
    search_input: Dict[str, Any],
    model: Type[models.Model],
) -> Tuple[Q, Dict[str, Any]]:
    """Build full-text search Q object."""
    from django.contrib.postgres.search import (
        SearchVector, SearchQuery, SearchRank
    )

    query_text = search_input.get("query", "")
    fields = search_input.get("fields", [])
    config = search_input.get("config", "english")
    rank_threshold = search_input.get("rank_threshold")
    search_type = search_input.get("search_type", "websearch")

    # Build search vector
    vector = SearchVector(*fields, config=config)
    query = SearchQuery(query_text, config=config, search_type=search_type)

    annotations = {
        "_search_vector": vector,
        "_search_rank": SearchRank(vector, query),
    }

    q = Q(_search_vector=query)

    if rank_threshold:
        q &= Q(_search_rank__gte=rank_threshold)

    return q, annotations
```

---

## Phase 3: Filter Presets

**Priority:** P1 - Medium Impact
**Estimated Complexity:** Low
**Files to modify:**

- `rail_django/generators/filter_inputs.py`
- `rail_django/core/meta.py` (add presets to GraphQLMeta)

### Description

Define reusable filter configurations in model's GraphQLMeta class.

### Implementation Steps

1. Add `filter_presets` attribute to GraphQLMeta
2. Add `presets` argument to list queries
3. Merge preset filters with user-provided filters
4. Support combining multiple presets

### GraphQLMeta Configuration

```python
class OrderMeta(GraphQLMeta):
    filter_presets = {
        "recent": {
            "created_at": {"this_month": True}
        },
        "high_value": {
            "total": {"gte": 1000}
        },
        "pending": {
            "status": {"in_": ["pending", "processing"]}
        },
        "priority": {
            "AND": [
                {"total": {"gte": 500}},
                {"status": {"eq": "pending"}}
            ]
        },
    }
```

### Usage Examples

```graphql
# Use single preset
query {
  orders(presets: ["recent"]) {
    id
    created_at
  }
}

# Combine multiple presets (AND logic)
query {
  orders(presets: ["recent", "high_value"]) {
    id
    total
    created_at
  }
}

# Combine preset with custom filters
query {
  orders(
    presets: ["high_value"]
    where: { customer_rel: { country: { eq: "US" } } }
  ) {
    id
    total
    customer {
      name
    }
  }
}

# Override preset values with custom filters
query {
  orders(
    presets: ["recent"]
    where: { created_at: { this_week: true } } # Overrides this_month
  ) {
    id
    created_at
  }
}
```

### Backend Implementation

```python
def _apply_presets(
    self,
    where_input: Dict[str, Any],
    presets: List[str],
    model: Type[models.Model],
) -> Dict[str, Any]:
    """Merge preset filters with user-provided filters."""
    graphql_meta = get_model_graphql_meta(model)
    preset_defs = getattr(graphql_meta, "filter_presets", {})

    merged = {}

    # Apply presets in order
    for preset_name in presets:
        if preset_name in preset_defs:
            merged = self._deep_merge(merged, preset_defs[preset_name])

    # User filters override presets
    merged = self._deep_merge(merged, where_input)

    return merged
```

---

## Phase 4: Distinct On

**Priority:** P1 - Medium Impact
**Estimated Complexity:** Low
**Files to modify:**

- `rail_django/generators/queries_list.py`

### Description

Deduplicate results by specific fields (Postgres `DISTINCT ON`).

### Implementation Steps

1. Add `distinct_on` argument to list queries
2. Implement Postgres-specific `DISTINCT ON` clause
3. Add fallback using subquery for other databases
4. Validate that distinct fields are in ordering

### Usage Examples

```graphql
# Get one product per brand (latest by created_at)
query {
  products(distinct_on: ["brand"], order_by: ["brand", "-created_at"]) {
    id
    brand
    name
    created_at
  }
}

# Get latest order per customer
query {
  orders(
    distinct_on: ["customer_id"]
    order_by: ["customer_id", "-created_at"]
  ) {
    id
    customer {
      name
    }
    created_at
    total
  }
}

# Distinct with filtering
query {
  products(
    where: { price: { gte: 100 } }
    distinct_on: ["category_id"]
    order_by: ["category_id", "-rating"]
  ) {
    id
    category {
      name
    }
    name
    rating
  }
}

# Multiple distinct fields
query {
  sales(
    distinct_on: ["region", "product_category"]
    order_by: ["region", "product_category", "-amount"]
  ) {
    id
    region
    product_category
    amount
  }
}
```

### Backend Implementation

```python
def _apply_distinct_on(
    self,
    queryset: models.QuerySet,
    distinct_on: List[str],
    order_by: List[str],
) -> models.QuerySet:
    """Apply DISTINCT ON clause (Postgres only)."""
    from django.db import connection

    if connection.vendor == "postgresql":
        # Validate: distinct_on fields must be prefix of order_by
        return queryset.order_by(*order_by).distinct(*distinct_on)
    else:
        # Fallback: use subquery with window function
        from django.db.models import Window, RowNumber
        from django.db.models.functions import RowNumber

        partition_by = [F(f) for f in distinct_on]
        order_by_exprs = self._parse_order_by(order_by)

        annotated = queryset.annotate(
            _row_num=Window(
                expression=RowNumber(),
                partition_by=partition_by,
                order_by=order_by_exprs,
            )
        )
        return annotated.filter(_row_num=1)
```

---

## Phase 5: Computed/Expression Filters

**Priority:** P1 - Medium Impact
**Estimated Complexity:** Medium
**Files to modify:**

- `rail_django/generators/filter_inputs.py`
- `rail_django/core/meta.py`

### Description

Filter by database expressions and computed values without storing them.

### Implementation Steps

1. Add `computed_filters` to GraphQLMeta
2. Generate filter inputs for computed fields
3. Add annotations to queryset before filtering
4. Support common expressions (F, Value, Case/When, functions)

### GraphQLMeta Configuration

```python
from django.db.models import F, Value, ExpressionWrapper, FloatField
from django.db.models.functions import Now, Extract

class ProductMeta(GraphQLMeta):
    computed_filters = {
        "profit_margin": {
            "expression": ExpressionWrapper(
                F("price") - F("cost"),
                output_field=FloatField()
            ),
            "filter_type": "float",
            "description": "Profit margin (price - cost)",
        },
        "profit_percentage": {
            "expression": ExpressionWrapper(
                (F("price") - F("cost")) / F("cost") * 100,
                output_field=FloatField()
            ),
            "filter_type": "float",
            "description": "Profit percentage",
        },
        "age_days": {
            "expression": Extract(Now() - F("created_at"), "day"),
            "filter_type": "int",
            "description": "Days since creation",
        },
        "is_on_sale": {
            "expression": Case(
                When(discount__gt=0, then=Value(True)),
                default=Value(False),
            ),
            "filter_type": "boolean",
            "description": "Whether product has discount",
        },
    }
```

### Usage Examples

```graphql
# Filter by profit margin
query {
  products(where: { profit_margin: { gte: 50 } }) {
    id
    name
    price
    cost
  }
}

# Filter by profit percentage
query {
  products(where: { profit_percentage: { gte: 20, lte: 50 } }) {
    id
    name
  }
}

# Filter by age in days
query {
  products(
    where: {
      age_days: { lte: 30 } # Created in last 30 days
    }
  ) {
    id
    name
    created_at
  }
}

# Combined computed and regular filters
query {
  products(
    where: {
      is_on_sale: { eq: true }
      profit_margin: { gte: 25 }
      category_rel: { name: { eq: "Electronics" } }
    }
  ) {
    id
    name
    price
    discount
  }
}

# Computed filter with ordering
query {
  products(
    where: { profit_percentage: { gte: 10 } }
    order_by: ["-profit_percentage"]
  ) {
    id
    name
  }
}
```

### Backend Implementation

```python
def _apply_computed_filters(
    self,
    queryset: models.QuerySet,
    where_input: Dict[str, Any],
    model: Type[models.Model],
) -> models.QuerySet:
    """Apply computed field annotations and filters."""
    graphql_meta = get_model_graphql_meta(model)
    computed_defs = getattr(graphql_meta, "computed_filters", {})

    annotations = {}

    for field_name, definition in computed_defs.items():
        if field_name in where_input:
            annotations[field_name] = definition["expression"]

    if annotations:
        queryset = queryset.annotate(**annotations)

    return queryset
```

---

## Phase 6: Filter Introspection API

**Priority:** P2 - Medium Impact
**Estimated Complexity:** Low
**Files to modify:**

- `rail_django/generators/filter_inputs.py`
- `rail_django/extensions/metadata.py`

### Description

Expose available filters programmatically for dynamic UI generation.

### Implementation Steps

1. Create `FilterSchemaType` GraphQL type
2. Add `__filterSchema` query
3. Include field types, available operators, and presets
4. Support nested relation introspection

### New GraphQL Types

```python
class FilterOperatorType(graphene.ObjectType):
    name = graphene.String()
    description = graphene.String()
    input_type = graphene.String()
    is_array = graphene.Boolean()

class FilterFieldType(graphene.ObjectType):
    name = graphene.String()
    field_type = graphene.String()
    description = graphene.String()
    operators = graphene.List(FilterOperatorType)
    is_relation = graphene.Boolean()
    related_model = graphene.String()

class FilterPresetType(graphene.ObjectType):
    name = graphene.String()
    description = graphene.String()
    filter_json = graphene.JSONString()

class FilterSchemaType(graphene.ObjectType):
    model = graphene.String()
    fields = graphene.List(FilterFieldType)
    presets = graphene.List(FilterPresetType)
    supports_fts = graphene.Boolean()
    supports_aggregation = graphene.Boolean()
```

### Usage Examples

```graphql
# Get filter schema for a model
query {
  __filterSchema(model: "Product") {
    model
    fields {
      name
      field_type
      operators {
        name
        description
        input_type
      }
      is_relation
      related_model
    }
    presets {
      name
      description
    }
    supports_fts
  }
}

# Get filter schema with nested relations
query {
  __filterSchema(model: "Order", depth: 2) {
    fields {
      name
      field_type
      operators {
        name
      }
      is_relation
      related_model
    }
  }
}
```

### Response Example

```json
{
  "__filterSchema": {
    "model": "Product",
    "fields": [
      {
        "name": "name",
        "field_type": "CharField",
        "operators": [
          {
            "name": "eq",
            "description": "Exact match",
            "input_type": "String"
          },
          {
            "name": "icontains",
            "description": "Case-insensitive contains",
            "input_type": "String"
          },
          {
            "name": "starts_with",
            "description": "Starts with",
            "input_type": "String"
          },
          { "name": "in_", "description": "In list", "input_type": "[String]" }
        ],
        "is_relation": false
      },
      {
        "name": "price",
        "field_type": "DecimalField",
        "operators": [
          { "name": "eq", "description": "Equal to", "input_type": "Float" },
          {
            "name": "gt",
            "description": "Greater than",
            "input_type": "Float"
          },
          {
            "name": "between",
            "description": "Between range",
            "input_type": "[Float]"
          }
        ],
        "is_relation": false
      },
      {
        "name": "category",
        "field_type": "ForeignKey",
        "operators": [
          { "name": "eq", "description": "Exact ID", "input_type": "ID" }
        ],
        "is_relation": true,
        "related_model": "Category"
      }
    ],
    "presets": [
      { "name": "on_sale", "description": "Products currently on sale" },
      { "name": "in_stock", "description": "Products with stock > 0" }
    ],
    "supports_fts": true
  }
}
```

---

## Phase 7: Saved Filters

**Priority:** P2 - Medium Impact
**Estimated Complexity:** Medium
**Files to modify:**

- `rail_django/models/` (new: saved_filters.py)
- `rail_django/generators/mutations.py`
- `rail_django/generators/queries_list.py`

### Description

Allow users to save and reuse filter configurations.

### Implementation Steps

1. Create `SavedFilter` model
2. Add mutations for CRUD operations
3. Add `savedFilter` argument to list queries
4. Support user-private and shared filters
5. Add filter validation before saving

### New Model

```python
class SavedFilter(models.Model):
    name = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    filter_json = models.JSONField()
    description = models.TextField(blank=True)

    # Ownership
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_filters"
    )
    is_shared = models.BooleanField(default=False)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    use_count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("name", "created_by", "model_name")]
```

### Usage Examples

```graphql
# Save a filter
mutation {
  saveFilter(
    input: {
      name: "high_value_pending"
      model: "Order"
      filter: { total: { gte: 1000 }, status: { eq: "pending" } }
      description: "High value orders awaiting processing"
      shared: true
    }
  ) {
    savedFilter {
      id
      name
    }
    success
  }
}

# Use saved filter
query {
  orders(savedFilter: "high_value_pending") {
    id
    total
    status
  }
}

# Use saved filter by ID
query {
  orders(savedFilterId: "abc123") {
    id
    total
  }
}

# Combine saved filter with additional filters
query {
  orders(
    savedFilter: "high_value_pending"
    where: { customer_rel: { vip: { eq: true } } }
  ) {
    id
    total
    customer {
      name
    }
  }
}

# List user's saved filters
query {
  mySavedFilters(model: "Order") {
    id
    name
    description
    use_count
    is_shared
  }
}

# List shared filters
query {
  sharedFilters(model: "Order") {
    id
    name
    description
    created_by {
      username
    }
  }
}

# Update saved filter
mutation {
  updateSavedFilter(id: "abc123", input: { filter: { total: { gte: 2000 } } }) {
    success
  }
}

# Delete saved filter
mutation {
  deleteSavedFilter(id: "abc123") {
    success
  }
}
```

---

## Phase 8: Geo/Distance Filters

**Priority:** P2 - Niche but High Value
**Estimated Complexity:** High
**Files to modify:**

- `rail_django/generators/filter_inputs.py`
- `rail_django/core/settings.py`

### Description

Geographic filtering for models with location data.

### Implementation Steps

1. Detect `django.contrib.gis` availability
2. Create `GeoFilterInput` types
3. Implement distance, bounding box, and polygon filters
4. Support both Point and Polygon geometries

### New Input Types

```python
class PointInput(graphene.InputObjectType):
    lat = graphene.Float(required=True)
    lng = graphene.Float(required=True)

class BoundingBoxInput(graphene.InputObjectType):
    sw = graphene.InputField(PointInput, required=True)
    ne = graphene.InputField(PointInput, required=True)

class GeoFilterInput(graphene.InputObjectType):
    distance_lte = graphene.InputField(
        lambda: DistanceFilterInput,
        description="Within distance from point"
    )
    distance_gte = graphene.InputField(
        lambda: DistanceFilterInput,
        description="Beyond distance from point"
    )
    within_bounds = graphene.InputField(
        BoundingBoxInput,
        description="Within bounding box"
    )
    within_polygon = graphene.List(
        PointInput,
        description="Within polygon (list of points)"
    )

class DistanceFilterInput(graphene.InputObjectType):
    point = graphene.InputField(PointInput, required=True)
    km = graphene.Float(description="Distance in kilometers")
    mi = graphene.Float(description="Distance in miles")
    m = graphene.Float(description="Distance in meters")
```

### Usage Examples

```graphql
# Find stores within 10km of a point
query {
  stores(
    where: {
      location: {
        distance_lte: { point: { lat: 48.8566, lng: 2.3522 }, km: 10 }
      }
    }
  ) {
    id
    name
    address
    _distance_km # Annotated distance
  }
}

# Find properties within bounding box
query {
  properties(
    where: {
      location: {
        within_bounds: {
          sw: { lat: 48.8, lng: 2.2 }
          ne: { lat: 48.9, lng: 2.4 }
        }
      }
    }
  ) {
    id
    address
    price
  }
}

# Find locations beyond 50km (exclude nearby)
query {
  warehouses(
    where: {
      location: {
        distance_gte: { point: { lat: 40.7128, lng: -74.0060 }, km: 50 }
      }
    }
  ) {
    id
    name
  }
}

# Combined geo and regular filters
query {
  restaurants(
    where: {
      location: {
        distance_lte: { point: { lat: 48.8566, lng: 2.3522 }, km: 5 }
      }
      rating: { gte: 4.0 }
      cuisine: { in_: ["Italian", "French"] }
    }
  ) {
    id
    name
    rating
    cuisine
  }
}

# Order by distance
query {
  stores(
    where: {
      location: {
        distance_lte: { point: { lat: 48.8566, lng: 2.3522 }, km: 20 }
      }
    }
    order_by: ["_distance"]
  ) {
    id
    name
    _distance_km
  }
}
```

---

## Implementation Timeline

| Phase | Feature              | Estimated Duration |
| ----- | -------------------- | ------------------ |
| 1     | Aggregation Filters  | 2-3 days           |
| 2     | Full-Text Search     | 1-2 days           |
| 3     | Filter Presets       | 1 day              |
| 4     | Distinct On          | 1 day              |
| 5     | Computed Filters     | 2 days             |
| 6     | Filter Introspection | 1-2 days           |
| 7     | Saved Filters        | 3-4 days           |
| 8     | Geo Filters          | 3-4 days           |

**Total Estimated Time:** 14-19 days

---

## Testing Strategy

Each phase should include:

1. **Unit Tests** (`rail_django/tests/unit/test_filter_*.py`)
   - Input type field validation
   - Q object generation
   - Edge cases (null values, empty lists)

2. **Integration Tests** (`rail_django/tests/integration/test_filter_*.py`)
   - End-to-end GraphQL queries
   - Database interaction
   - Performance benchmarks

3. **Documentation**
   - Update `docs/reference/filtering.md`
   - Add examples to `docs/guides/`

---

## Backwards Compatibility

All new features should be:

- Opt-in by default
- Configurable via `SchemaSettings`
- Gracefully degraded when database doesn't support feature

```python
# Schema settings
RAIL_SCHEMAS = {
    "default": {
        "filtering": {
            "enable_aggregation_filters": True,
            "enable_fts": True,
            "enable_geo_filters": False,  # Requires GIS
            "enable_computed_filters": True,
            "enable_saved_filters": True,
            "fts_config": "english",
            "max_filter_depth": 5,
        }
    }
}
```

---
