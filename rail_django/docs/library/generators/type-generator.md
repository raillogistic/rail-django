# Type Generator

> **Module Path:** `rail_django.generators.types.generator`

The TypeGenerator creates GraphQL types from Django models, including object types, input types, filter types, enums, and interfaces.

## Architecture Overview

```
                          TypeGenerator
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
   Object Types           Input Types            Filter Types
   (DjangoObjectType)    (InputObjectType)       (FilterSet)
        │                      │                      │
        ├──────────────────────┼──────────────────────┤
        │                      │                      │
        ▼                      ▼                      ▼
   Enum Types            Union Types            Interface Types
   (Graphene.Enum)       (Graphene.Union)      (Graphene.Interface)
```

## Class Reference

### TypeGenerator

```python
from rail_django.generators.types import TypeGenerator

# Create generator for default schema
type_gen = TypeGenerator(schema_name="default")

# Generate object type for a model
ProductType = type_gen.generate_object_type(Product)

# Generate input type for mutations
ProductInput = type_gen.generate_input_type(Product, mutation_type="create")

# Generate filter type
ProductFilter = type_gen.generate_filter_type(Product)
```

#### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `settings` | `TypeGeneratorSettings` | `None` | Type generation settings |
| `mutation_settings` | `MutationGeneratorSettings` | `None` | Mutation settings for inputs |
| `schema_name` | `str` | `"default"` | Schema identifier |

#### Key Properties

| Property | Type | Description |
|----------|------|-------------|
| `schema_name` | `str` | Current schema name |
| `settings` | `TypeGeneratorSettings` | Type generation settings |
| `mutation_settings` | `MutationGeneratorSettings` | Mutation generation settings |
| `custom_scalars` | `dict` | Enabled custom scalar types |
| `query_optimizer` | `QueryOptimizer` | Query optimization helper |

## Object Type Generation

### generate_object_type()

Creates a DjangoObjectType for a model:

```python
ProductType = type_gen.generate_object_type(Product)

# Generated type includes:
# - All exposed model fields
# - Relationship fields (ForeignKey, ManyToMany)
# - Reverse relations
# - Enum fields for choices
# - Custom scalar mappings
```

#### What Gets Generated

```python
# For this model:
class Product(models.Model):
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    tags = models.ManyToManyField(Tag)
    created_at = models.DateTimeField(auto_now_add=True)

# TypeGenerator creates:
class ProductType(DjangoObjectType):
    class Meta:
        model = Product
        fields = ["id", "name", "price", "status", "category", "tags", "created_at"]

    # Auto-generated enum for choices
    status = graphene.Field(ProductStatusEnum)

    # Optimized relation resolvers
    def resolve_category(self, info):
        # Uses select_related optimization
        ...

    def resolve_tags(self, info):
        # Uses prefetch_related optimization
        ...
```

#### Field Type Mapping

Django fields are mapped to GraphQL types:

| Django Field | GraphQL Type |
|-------------|--------------|
| `CharField` | `String` |
| `TextField` | `String` |
| `IntegerField` | `Int` |
| `FloatField` | `Float` |
| `DecimalField` | `Decimal` (custom scalar) |
| `BooleanField` | `Boolean` |
| `DateField` | `Date` (custom scalar) |
| `DateTimeField` | `DateTime` (custom scalar) |
| `TimeField` | `Time` (custom scalar) |
| `UUIDField` | `UUID` (custom scalar) |
| `EmailField` | `Email` (custom scalar) |
| `URLField` | `URL` (custom scalar) |
| `JSONField` | `JSON` (custom scalar) |
| `BinaryField` | `Binary` (custom scalar) |
| `FileField` | `String` (URL) |
| `ImageField` | `String` (URL) |
| `ForeignKey` | Related object type |
| `ManyToManyField` | List of related type |

#### Custom Field Mappings

Add custom mappings in settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "type_generation_settings": {
        "custom_field_mappings": {
            "myapp.fields.MoneyField": "Decimal",
            "myapp.fields.PhoneField": "Phone"
        }
    }
}
```

## Input Type Generation

### generate_input_type()

Creates input types for mutations:

```python
# Create input
CreateProductInput = type_gen.generate_input_type(
    Product,
    mutation_type="create"
)

# Update input (partial)
UpdateProductInput = type_gen.generate_input_type(
    Product,
    mutation_type="update",
    partial=True
)
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `Type[Model]` | Required | Django model class |
| `mutation_type` | `str` | `"create"` | `"create"` or `"update"` |
| `partial` | `bool` | `False` | Make all fields optional |
| `include_reverse_relations` | `bool` | `True` | Include nested inputs |
| `exclude_fields` | `list[str]` | `None` | Fields to exclude |
| `depth` | `int` | `0` | Current nesting depth |

#### Input Type Behavior

**Create Input:**
```graphql
input CreateProductInput {
  name: String!        # Required (no default, not blank)
  price: Decimal!      # Required
  status: String       # Optional (has default)
  categoryId: ID!      # Required FK
  tagIds: [ID]         # Optional M2M

  # Nested create (if enabled)
  items: [ProductItemInput]
}
```

**Update Input:**
```graphql
input UpdateProductInput {
  id: ID!              # Required for update
  name: String         # Optional
  price: Decimal       # Optional
  status: String       # Optional
  categoryId: ID       # Optional
  tagIds: [ID]         # Optional
}
```

### Nested Input Types

For related models, nested inputs are generated:

```python
# Enable in settings
"mutation_settings": {
    "enable_nested_relations": True
}
```

```graphql
input CreateOrderInput {
  customer: CustomerInput  # Nested create
  customerId: ID           # Or use existing
  items: [OrderItemInput!] # Nested list
}

input OrderItemInput {
  productId: ID!
  quantity: Int!
  price: Decimal
}
```

### Relation Input Types

The `RelationInputTypeGenerator` creates unified inputs:

```python
# Generated for each relation
input OrderItemsInput {
  set: [ID]              # Replace all
  add: [ID]              # Add to existing
  remove: [ID]           # Remove specific
  create: [OrderItemCreateInput]  # Create new
  update: [OrderItemUpdateInput]  # Update existing
  delete: [ID]           # Delete specific
}
```

## Filter Type Generation

### generate_filter_type()

Creates Django-filter FilterSets:

```python
ProductFilter = type_gen.generate_filter_type(Product)
```

#### Generated Filter

```python
class ProductFilter(FilterSet):
    class Meta:
        model = Product
        fields = {
            "name": ["exact", "icontains", "startswith"],
            "price": ["exact", "gt", "gte", "lt", "lte", "range"],
            "status": ["exact", "in"],
            "created_at": ["exact", "gt", "gte", "lt", "lte", "year", "month"],
            # ... more fields
        }
```

#### Filter Configuration

Filters are configured via GraphQLMeta:

```python
class Product(models.Model):
    class GraphQLMeta:
        filtering = GraphQLMetaConfig.Filtering(
            fields={
                "price": GraphQLMetaConfig.FilterField(
                    lookups=["gt", "lt", "between"]
                )
            }
        )
```

## Enum Generation

### Choice Field Enums

Automatically generated for choice fields:

```python
class Product(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("archived", "Archived")
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

# Generated enum:
class ProductStatusEnum(graphene.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
```

### Enum Registry

Enums are cached to avoid duplicates:

```python
# Get or create enum for a field
StatusEnum = type_gen._get_or_create_enum_for_field(Product, status_field)
```

## Type Registry

Generated types are cached:

```python
# Object types
type_gen._type_registry[Product]  # ProductType

# Input types
type_gen._input_type_registry[Product]  # ProductInput

# Filter types
type_gen._filter_type_registry[Product]  # ProductFilter

# Enums
type_gen._enum_registry["ProductStatus"]  # ProductStatusEnum
```

## Field Exclusion

### Global Exclusions

```python
RAIL_DJANGO_GRAPHQL = {
    "type_generation_settings": {
        "exclude_fields": {
            "Product": ["internal_notes", "cost_price"],
            "*": ["password"]  # All models
        }
    }
}
```

### GraphQLMeta Exclusions

```python
class Product(models.Model):
    class GraphQLMeta:
        fields = GraphQLMetaConfig.Fields(
            exclude=["internal_notes"]
        )
```

### Automatic Exclusions

- `polymorphic_ctype` (Django Polymorphic)
- Fields ending with `_ptr` (model inheritance)
- Fields marked as masked/hidden in access config

## Reverse Relations

Reverse relations are automatically included:

```python
# Model
class Order(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)

# Generated on CustomerType:
class CustomerType(DjangoObjectType):
    orders = graphene.List(OrderType)  # Reverse relation

    def resolve_orders(self, info):
        return self.order_set.all()
```

### Excluding Reverse Relations

```python
class Customer(models.Model):
    class GraphQLMeta:
        fields = GraphQLMetaConfig.Fields(
            exclude=["order_set"]  # Exclude reverse relation
        )
```

## DataLoader Integration

For performance, DataLoaders batch relation queries:

```python
# Automatically used for reverse relations
def resolve_orders(self, info):
    loader = type_gen._get_relation_dataloader(
        info.context,
        Order,
        self._meta.model._meta.get_field("customer"),
        self._state
    )
    if loader:
        return loader.load(self.id)
    return self.order_set.all()
```

## Multitenancy Support

Tenant scoping is applied to relations:

```python
def resolve_orders(self, info):
    qs = self.order_set.all()
    # Apply tenant filter
    qs = type_gen._apply_tenant_scope(qs, info, Order)
    return qs
```

## Custom Scalars

The generator uses enabled custom scalars:

```python
# From settings
"custom_scalars": {
    "DateTime": {"enabled": True},
    "Date": {"enabled": True},
    "JSON": {"enabled": True},
    "Decimal": {"enabled": True}
}

# Updates field type map
type_gen.custom_scalars  # {"DateTime": DateTimeScalar, ...}
```

## Settings Reference

### TypeGeneratorSettings

```python
@dataclass
class TypeGeneratorSettings:
    # Field exclusions by model
    exclude_fields: dict[str, list[str]] = field(default_factory=dict)
    excluded_fields: dict[str, list[str]] = field(default_factory=dict)  # Alias

    # Field inclusions (whitelist)
    include_fields: Optional[dict[str, list[str]]] = None

    # Custom field type mappings
    custom_field_mappings: dict = field(default_factory=dict)

    # Enable filter generation
    generate_filters: bool = True
    enable_filtering: bool = True  # Alias

    # Auto camelCase field names
    auto_camelcase: bool = True

    # Use help_text as field descriptions
    generate_descriptions: bool = True
```

## Usage Examples

### Basic Type Generation

```python
from rail_django.generators.types import TypeGenerator
from myapp.models import Product, Order

type_gen = TypeGenerator(schema_name="default")

# Generate types
ProductType = type_gen.generate_object_type(Product)
OrderType = type_gen.generate_object_type(Order)

# Generate inputs
ProductInput = type_gen.generate_input_type(Product, mutation_type="create")
ProductUpdateInput = type_gen.generate_input_type(Product, mutation_type="update", partial=True)
```

### With Custom Settings

```python
from rail_django.generators.types import TypeGenerator
from rail_django.core.settings import TypeGeneratorSettings

settings = TypeGeneratorSettings(
    exclude_fields={
        "Product": ["internal_notes", "cost_price"],
        "Order": ["internal_reference"]
    },
    custom_field_mappings={
        MoneyField: Decimal
    }
)

type_gen = TypeGenerator(settings=settings, schema_name="custom")
```

### Accessing Generated Types

```python
# Check if type exists
if Product in type_gen._type_registry:
    ProductType = type_gen._type_registry[Product]

# Get or generate
ProductType = type_gen.generate_object_type(Product)  # Cached on second call
```

## Internal Methods

### Field Analysis

```python
# Get excluded fields for a model
excluded = type_gen._get_excluded_fields(Product)

# Get included fields (whitelist)
included = type_gen._get_included_fields(Product)

# Check if field should be included
should_include = type_gen._should_include_field(Product, "name")
should_include_input = type_gen._should_include_field(Product, "name", for_input=True)
```

### Meta Access

```python
# Get GraphQLMeta for a model (cached)
meta = type_gen._get_model_meta(Product)

# Get maskable fields (hidden/redacted)
maskable = type_gen._get_maskable_fields(Product)
```

### Reverse Relations

```python
# Get reverse relations for a model
reverse = type_gen._get_reverse_relations(Product)
# {"order_set": {"model": Order, "relation": ...}}
```

## Related Modules

- [Schema Builder](../core/schema-builder.md) - Uses TypeGenerator
- [Query Generator](./query-generator.md) - Uses generated types
- [Mutation Generator](./mutation-generator.md) - Uses generated inputs
- [GraphQLMeta](../core/graphql-meta.md) - Field configuration
- [Custom Scalars](../core/scalars.md) - Scalar type details
