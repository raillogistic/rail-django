# GraphQLMeta Reference

> **Module Path:** `rail_django.core.meta`

GraphQLMeta is the per-model configuration system that controls how each Django model is exposed in the GraphQL API. It provides fine-grained control over field exposure, filtering, ordering, permissions, and more.

## Overview

Define a `GraphQLMeta` (or `GraphqlMeta`) inner class on your Django model:

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Product(models.Model):
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=50, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    internal_notes = models.TextField(blank=True)

    class GraphQLMeta(GraphQLMetaConfig):
        fields = GraphQLMetaConfig.Fields(
            exclude=["internal_notes", "cost_price"],
            read_only=["sku", "created_at"]
        )
        filtering = GraphQLMetaConfig.Filtering(
            quick=["name", "sku"],
            fields={
                "price": GraphQLMetaConfig.FilterField(lookups=["gt", "lt", "between"])
            }
        )
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "price", "created_at"],
            default=["-created_at"]
        )
```

## Configuration Sections

### Fields Configuration

Control which fields are exposed and how:

```python
class GraphQLMeta(GraphQLMetaConfig):
    fields = GraphQLMetaConfig.Fields(
        # Fields to completely exclude from GraphQL
        exclude=["password_hash", "internal_notes"],

        # Fields included in queries only (not mutations)
        read_only=["created_at", "updated_at", "sku"],

        # Explicit list of fields to include (excludes all others)
        include=["id", "name", "email", "status"],

        # Fields required in create mutations
        required_create=["name", "email"],

        # Fields required in update mutations
        required_update=["id"]
    )
```

| Option | Type | Description |
|--------|------|-------------|
| `exclude` | `list[str]` | Fields never exposed in GraphQL |
| `read_only` | `list[str]` | Fields exposed in queries but not mutations |
| `include` | `list[str]` | Explicit allowlist (excludes all others) |
| `required_create` | `list[str]` | Fields required for create mutations |
| `required_update` | `list[str]` | Fields required for update mutations |

### Filtering Configuration

Control filtering capabilities for queries:

```python
class GraphQLMeta(GraphQLMetaConfig):
    filtering = GraphQLMetaConfig.Filtering(
        # Fields enabled for quick search (icontains)
        quick=["name", "description", "sku"],

        # Per-field filter configuration
        fields={
            "status": GraphQLMetaConfig.FilterField(
                lookups=["eq", "in", "is_null"],
                choices=["draft", "active", "archived"]
            ),
            "price": GraphQLMetaConfig.FilterField(
                lookups=["gt", "gte", "lt", "lte", "between"]
            ),
            "created_at": GraphQLMetaConfig.FilterField(
                lookups=["gte", "lte", "year", "month"]
            ),
            "category": GraphQLMetaConfig.FilterField(
                lookups=["eq", "in"],
                nested=True  # Enable nested relation filtering
            )
        },

        # Maximum filter depth for nested relations
        max_depth=3,

        # Enable/disable relation filtering
        enable_relation_filters=True
    )
```

#### Available Filter Lookups

| Lookup | Description | Example |
|--------|-------------|---------|
| `eq` | Exact match | `where: { status: { eq: "active" } }` |
| `in` | List match | `where: { status: { in: ["active", "pending"] } }` |
| `is_null` | Null check | `where: { email: { isNull: false } }` |
| `gt`, `gte` | Greater than | `where: { price: { gt: 100 } }` |
| `lt`, `lte` | Less than | `where: { price: { lte: 500 } }` |
| `between` | Range | `where: { price: { between: [100, 500] } }` |
| `contains` | Case-sensitive contains | `where: { name: { contains: "phone" } }` |
| `icontains` | Case-insensitive contains | `where: { name: { icontains: "phone" } }` |
| `starts_with` | Starts with | `where: { sku: { startsWith: "PRD-" } }` |
| `istarts_with` | Case-insensitive starts with | `where: { sku: { iStartsWith: "prd-" } }` |
| `ends_with` | Ends with | `where: { email: { endsWith: "@company.com" } }` |
| `iends_with` | Case-insensitive ends with | `where: { email: { iEndsWith: "@Company.com" } }` |
| `year` | Date year | `where: { createdAt: { year: 2024 } }` |
| `month` | Date month | `where: { createdAt: { month: 12 } }` |
| `day` | Date day | `where: { createdAt: { day: 25 } }` |

### Ordering Configuration

Control sorting capabilities:

```python
class GraphQLMeta(GraphQLMetaConfig):
    ordering = GraphQLMetaConfig.Ordering(
        # Fields allowed for ordering
        allowed=["name", "price", "created_at", "category__name"],

        # Default ordering when not specified
        default=["-created_at", "name"],

        # Maximum number of ordering fields
        max_fields=3,

        # Allow ordering by Python properties (slower)
        allow_property_ordering=False
    )
```

### Access Control Configuration

Define operation and field-level permissions:

```python
class GraphQLMeta(GraphQLMetaConfig):
    access = GraphQLMetaConfig.Access(
        # Operation-level guards
        operations={
            "list": GraphQLMetaConfig.OperationAccess(
                roles=["viewer", "editor", "admin"],
                permissions=["store.view_product"]
            ),
            "create": GraphQLMetaConfig.OperationAccess(
                roles=["editor", "admin"],
                permissions=["store.add_product"]
            ),
            "update": GraphQLMetaConfig.OperationAccess(
                roles=["editor", "admin"],
                permissions=["store.change_product"]
            ),
            "delete": GraphQLMetaConfig.OperationAccess(
                roles=["admin"],
                permissions=["store.delete_product"]
            )
        },

        # Field-level access rules
        fields=[
            GraphQLMetaConfig.FieldAccess(
                field="cost_price",
                access="read",
                visibility="hidden",
                roles=["finance", "admin"]
            ),
            GraphQLMetaConfig.FieldAccess(
                field="email",
                access="read",
                visibility="masked",
                mask_value="***@***.***",
                roles=["support"]
            ),
            GraphQLMetaConfig.FieldAccess(
                field="salary",
                access="none",
                visibility="hidden",
                roles=["hr_admin"]
            )
        ]
    )
```

#### Operation Access Options

| Option | Type | Description |
|--------|------|-------------|
| `roles` | `list[str]` | Roles allowed to perform operation |
| `permissions` | `list[str]` | Django permissions required |
| `guard` | `str` | Dotted path to guard function |
| `require_authentication` | `bool` | Whether auth is required |

#### Field Access Options

| Option | Type | Description |
|--------|------|-------------|
| `field` | `str` | Field name |
| `access` | `str` | Access level: `"read"`, `"write"`, `"none"` |
| `visibility` | `str` | How field appears: `"visible"`, `"masked"`, `"hidden"` |
| `mask_value` | `str` | Value shown when masked |
| `roles` | `list[str]` | Roles that bypass restrictions |

### Classification Configuration

Tag fields with data classifications:

```python
class GraphQLMeta(GraphQLMetaConfig):
    classifications = GraphQLMetaConfig.Classification(
        # Model-level classifications
        model=["pii", "sensitive"],

        # Field-level classifications
        fields={
            "email": ["pii", "contact"],
            "salary": ["financial", "restricted"],
            "social_security_number": ["pii", "highly_sensitive"]
        }
    )
```

Classifications can be used by:
- Security policies to auto-apply restrictions
- Audit logging to track sensitive data access
- Compliance reporting

### Custom Resolvers

Override default resolvers:

```python
class GraphQLMeta(GraphQLMetaConfig):
    resolvers = {
        # Custom field resolver
        "full_name": "myapp.resolvers.resolve_full_name",

        # Custom list resolver
        "__list__": "myapp.resolvers.custom_product_list",

        # Custom single resolver
        "__single__": "myapp.resolvers.custom_product_detail"
    }
```

### Custom Mutations

Configure mutation behavior:

```python
class GraphQLMeta(GraphQLMetaConfig):
    mutations = GraphQLMetaConfig.Mutations(
        # Disable specific mutations
        enable_create=True,
        enable_update=True,
        enable_delete=False,

        # Custom mutation handlers
        handlers={
            "create": "myapp.mutations.custom_create_product",
            "update": "myapp.mutations.custom_update_product"
        },

        # Pre/post hooks
        hooks={
            "pre_create": "myapp.hooks.before_product_create",
            "post_create": "myapp.hooks.after_product_create",
            "pre_update": "myapp.hooks.before_product_update",
            "post_update": "myapp.hooks.after_product_update",
            "pre_delete": "myapp.hooks.before_product_delete",
            "post_delete": "myapp.hooks.after_product_delete"
        }
    )
```

### Field Groups

Organize fields for frontend consumption:

```python
class GraphQLMeta(GraphQLMetaConfig):
    field_groups = [
        {
            "key": "basic",
            "label": "Basic Information",
            "fields": ["name", "sku", "price"]
        },
        {
            "key": "details",
            "label": "Product Details",
            "fields": ["description", "category", "tags"]
        },
        {
            "key": "inventory",
            "label": "Inventory",
            "fields": ["stock_quantity", "reorder_level"]
        }
    ]
```

### Custom Metadata

Pass arbitrary metadata to frontends:

```python
class GraphQLMeta(GraphQLMetaConfig):
    custom_metadata = {
        "icon": "shopping-cart",
        "color": "#4A90D9",
        "display_mode": "table",
        "actions": ["export", "print", "archive"]
    }
```

## Complete Example

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Order(models.Model):
    reference = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=[
        ("draft", "Draft"),
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled")
    ])
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    internal_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class GraphQLMeta(GraphQLMetaConfig):
        # Field exposure
        fields = GraphQLMetaConfig.Fields(
            exclude=["internal_notes"],
            read_only=["reference", "created_at", "updated_at", "total_amount"]
        )

        # Filtering
        filtering = GraphQLMetaConfig.Filtering(
            quick=["reference", "customer__name"],
            fields={
                "status": GraphQLMetaConfig.FilterField(
                    lookups=["eq", "in"],
                    choices=["draft", "pending", "confirmed", "shipped", "delivered", "cancelled"]
                ),
                "total_amount": GraphQLMetaConfig.FilterField(
                    lookups=["gt", "gte", "lt", "lte", "between"]
                ),
                "created_at": GraphQLMetaConfig.FilterField(
                    lookups=["gte", "lte", "year", "month"]
                ),
                "customer": GraphQLMetaConfig.FilterField(
                    lookups=["eq"],
                    nested=True
                )
            }
        )

        # Ordering
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["reference", "status", "total_amount", "created_at"],
            default=["-created_at"]
        )

        # Access control
        access = GraphQLMetaConfig.Access(
            operations={
                "list": GraphQLMetaConfig.OperationAccess(
                    roles=["order_viewer", "order_manager", "admin"]
                ),
                "create": GraphQLMetaConfig.OperationAccess(
                    roles=["order_manager", "admin"]
                ),
                "update": GraphQLMetaConfig.OperationAccess(
                    roles=["order_manager", "admin"]
                ),
                "delete": GraphQLMetaConfig.OperationAccess(
                    roles=["admin"]
                )
            }
        )

        # Classifications
        classifications = GraphQLMetaConfig.Classification(
            model=["transactional"],
            fields={
                "customer": ["pii_reference"],
                "total_amount": ["financial"]
            }
        )

        # UI hints
        field_groups = [
            {"key": "header", "label": "Order Header", "fields": ["reference", "customer", "status"]},
            {"key": "financial", "label": "Financial", "fields": ["total_amount"]},
            {"key": "timestamps", "label": "Timestamps", "fields": ["created_at", "updated_at"]}
        ]

        custom_metadata = {
            "icon": "shopping-bag",
            "color": "#28A745"
        }
```

## YAML Configuration

GraphQLMeta can also be defined in `meta.yaml`:

```yaml
# apps/store/meta.yaml
models:
  Product:
    fields:
      exclude:
        - internal_notes
        - cost_price
      read_only:
        - sku
        - created_at
    filtering:
      quick:
        - name
        - sku
      fields:
        status:
          lookups:
            - eq
            - in
          choices:
            - draft
            - active
        price:
          lookups:
            - gt
            - lt
            - between
    ordering:
      allowed:
        - name
        - price
        - created_at
      default:
        - -created_at
    access:
      operations:
        list:
          roles:
            - catalog_viewer
        update:
          roles:
            - catalog_admin
      fields:
        - field: cost_price
          access: read
          visibility: hidden
          roles:
            - finance_admin

  Order:
    fields:
      exclude:
        - internal_notes
    ordering:
      default:
        - -created_at

roles:
  catalog_viewer:
    description: Read-only access to catalog
    permissions:
      - store.view_product
  catalog_admin:
    description: Full catalog management
    permissions:
      - store.*
```

## Programmatic Access

Get GraphQLMeta configuration programmatically:

```python
from rail_django.core.meta import get_model_graphql_meta

# Get meta for a model
meta = get_model_graphql_meta(Product)

# Check if field should be exposed
if meta.should_expose_field("price"):
    print("Price is exposed")

# Get filtering config
filtering = meta.filtering
print(f"Quick search fields: {filtering.quick}")

# Get ordering config
ordering = meta.ordering
print(f"Default order: {ordering.default}")

# Check operation access
if meta.can_perform_operation("delete", user):
    print("User can delete")
```

## Precedence Rules

When multiple configuration sources exist:

1. **Code-defined GraphQLMeta** (highest priority)
2. **YAML/JSON meta configuration**
3. **Global settings** (RAIL_DJANGO_GRAPHQL)
4. **Library defaults** (lowest priority)

## Helper Methods

The GraphQLMeta helper provides utility methods:

```python
meta = get_model_graphql_meta(Product)

# Check field exposure
meta.should_expose_field("name")           # True/False
meta.should_expose_field("name", for_input=True)  # For mutations

# Get excluded fields
excluded = meta.get_excluded_fields()      # ['internal_notes', 'cost_price']

# Get read-only fields
read_only = meta.get_read_only_fields()    # ['sku', 'created_at']

# Check operation guards
has_guard = meta.has_operation_guard("create")

# Get field access rules
rules = meta.get_field_access_rules("email")
```

## Related Modules

- [Type Generator](../generators/type-generator.md) - Uses meta for type creation
- [Query Generator](../generators/query-generator.md) - Uses meta for filtering/ordering
- [Mutation Generator](../generators/mutation-generator.md) - Uses meta for field rules
- [RBAC System](../security/rbac.md) - Access control integration
- [Field Permissions](../security/field-permissions.md) - Field-level security
