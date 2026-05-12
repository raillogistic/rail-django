# Models and Schema Reference

Rail Django uses a "Model-First" approach. You define standard Django models, and the framework automatically generates the corresponding GraphQL schema (Types, Queries, and Mutations) using the `TypeGenerator`.

## Automatic Enhancements

The generator adds helper fields based on model definitions:
1. **Display Labels**: For fields with `choices`, it adds a `*Desc` field (e.g., `statusDesc` for `status`).
2. **Counts**: For `ManyToMany` and reverse relationships, it adds a `*Count` field (e.g., `ordersCount`).
3. **Polymorphism**: Adds `polymorphicType` for inherited models.
4. **Custom Output Fields**: Decorated model methods can expose explicit GraphQL fields.

**Naming Convention**: Rail Django converts all python `snake_case` field names to **`camelCase`** in the GraphQL schema by default.

## `GraphQLMeta` Configuration

Customize how a model is exposed by defining a `GraphQLMeta` class within the model. It controls field exposure, filtering, ordering, operation guards, relation operation policy, and metadata exported to clients.

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta
from django.db.models.functions import Now
from datetime import timedelta

class Order(models.Model):
    order_number = models.CharField(max_length=64, unique=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    internal_notes = models.TextField(blank=True)
    risk_score = models.IntegerField(default=0)
    placed_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def can_access_order(user=None, instance=None, **kwargs):
        return True # custom logic

    class GraphQLMeta(RailGraphQLMeta):
        # 1. Field Exposure (FieldExposureConfig)
        fields = RailGraphQLMeta.Fields(
            include=["id", "order_number", "total_amount", "placed_at"],
            read_only=["order_number", "placed_at"],
            exclude=["internal_notes"],
            write_only=[]
        )

        # 2. Filtering (FilteringConfig)
        filtering = RailGraphQLMeta.Filtering(
            quick=["order_number"], # Fields for the 'quick' search argument
            fields={
                "total_amount": RailGraphQLMeta.FilterField(lookups=["eq", "gt", "lt", "between"])
            },
            presets={
                "high_value": {"total_amount": {"gte": 1000}}
            },
            custom={
                "overdue": "filter_overdue" # Reference to a model method
            }
        )

        # 3. Computed Filters (Django Expressions)
        computed_filters = {
            "is_recent": {
                "expression": models.Q(placed_at__gte=Now() - timedelta(days=7)),
                "filter_type": "boolean"
            }
        }

        # 4. Ordering (OrderingConfig)
        ordering = RailGraphQLMeta.Ordering(
            allowed=["placed_at", "total_amount"],
            default=["-placed_at"]
        )

        # 5. Access Control (AccessControlConfig)
        access = RailGraphQLMeta.AccessControl(
            operations={
                "create": RailGraphQLMeta.OperationGuard(
                    roles=["order_manager"],
                    permissions=["store.add_order"]
                ),
                "retrieve": RailGraphQLMeta.OperationGuard(
                    condition="can_access_order" # Reference to staticmethod
                ),
                "list": RailGraphQLMeta.OperationGuard(
                    allow_anonymous=False
                )
            },
            fields=[
                RailGraphQLMeta.FieldGuard(
                    field="risk_score",
                    access="read",
                    visibility="hidden", # or "masked"
                    roles=["admin"]
                )
            ]
        )

        # 6. Resolvers (ResolverConfig)
        resolvers = RailGraphQLMeta.Resolvers(
            queries={"priority_queue": "resolve_priority_queue"},
            mutations={},
            fields={"full_name": "resolve_full_name"}
        )

        # 7. Relation Operation Policy (FieldRelationConfig)
        relations = {
            "items": RailGraphQLMeta.FieldRelation(
                style="unified", # or "id_only"
                connect=RailGraphQLMeta.RelationOperation(enabled=True),
                create=RailGraphQLMeta.RelationOperation(enabled=False),
                update=RailGraphQLMeta.RelationOperation(enabled=False),
                disconnect=RailGraphQLMeta.RelationOperation(enabled=True),
                set=RailGraphQLMeta.RelationOperation(enabled=True),
            )
        }

        # 8. Classification (ClassificationConfig)
        classifications = RailGraphQLMeta.Classification(
            model=["customer-data"],
            fields={"risk_score": ["sensitive", "financial"]}
        )

        # 9. ABAC Policies
        abac_policies = [
            {
                "name": "same_department_only",
                "effect": "allow",
                "priority": 60,
                "subject_conditions": {
                    "department": {
                        "operator": "eq",
                        "target": "resource.department",
                    }
                },
            }
        ]

        # 10. Multi-tenancy
        tenant_field = "organization" # Field path used by multitenancy integrations. Set to None to disable.
```

### `GraphQLMeta` Detailed Breakdown

- **Fields**: Controls visibility.
  - `include`: Explicit list of fields to expose.
  - `exclude`: Fields to hide entirely.
  - `read_only`: Exposed in Queries, hidden in Mutation inputs.
  - `write_only`: Hidden in Queries, exposed in Mutation inputs.
- **Filtering**: Controls filter capabilities.
  - `quick`: List of fields searched when using the `quick` argument.
  - `fields`: Specific lookups allowed per field (e.g., `["eq", "in"]`).
  - `presets`: Map of named pre-defined filter sets.
  - `custom`: Map of filter names to model methods.
- **Computed Filters**: Define complex filters using Django expressions (like `Q` objects or `ExpressionWrapper`).
- **AccessControl**: Contains `operations` and `fields` guards.
  - `operations`: Dict mapping standard operations (`list`, `retrieve`, `create`, `update`, `delete`) to `OperationGuard` objects which can define `roles`, `permissions`, a custom `condition` method, and `match` ("any" or "all").
  - `fields`: List of `FieldGuard` objects to control `visibility` ("visible", "hidden", "masked") based on `roles` or `access` ("read", "write").
- **Relations**: Defines the policy for nested operations (e.g., disable `create` or `update` on a reverse foreign key to prevent errors when the FK cannot be null). Use `style="id_only"` to disable nested `create`/`update`.
- **Classification**: Tag models and fields with classifications to apply broad security policies across your app (e.g., tag fields as "pii" and create a global policy restricting "pii" access).

## Custom Output Fields (`@field`)

Use the `@field` decorator from `rail_django.core.decorators` to define custom computed fields on your model with explicit Graphene types.

```python
import graphene
from rail_django.core.decorators import field

class Employee(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    @field(type=graphene.String, title="Summary")
    def summary(self) -> str:
        return f"{self.first_name} {self.last_name}"

    class GraphQLMeta(RailGraphQLMeta):
        fields = RailGraphQLMeta.Fields(include=["first_name", "last_name", "summary"])
```

## Relationships & N+1 Prevention

Rail Django automatically handles relationships (`ForeignKey`, `ManyToManyField`):
- **Forward Relations**: Nested types (`product.category`).
- **Reverse Relations**: List fields (`category.products`).

The framework analyzes the GraphQL selection set and automatically applies `select_related` and `prefetch_related` to the Django QuerySet to solve N+1 query problems out of the box.

## Enums
Django `TextChoices` and `IntegerChoices` are automatically converted to GraphQL Enums.

## Registering Schemas (`@register_schema`)
You can use the `@register_schema` decorator from `rail_django.core.decorators` to register GraphQL schemas with the central schema registry. It can be applied to schema classes or schema factory functions.

```python
import graphene
from rail_django.core.decorators import register_schema

@register_schema(
    name="blog_schema",
    description="Blog management GraphQL schema",
    version="2.0.0",
    apps=["blog", "comments"],
    settings={"enable_graphiql": True, "authentication_required": False}
)
class BlogSchema(graphene.Schema):
    query = BlogQuery
    mutation = BlogMutation
```