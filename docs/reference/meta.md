# GraphQLMeta Reference

`GraphQLMeta` is the configuration hub for each model. It allows you to declare how the framework should treat the model in the GraphQL schema.

## Full Reference

```python
class Order(models.Model):
    class GraphQLMeta:
        # 1. Field Exposure
        fields = GraphQLMeta.Fields(
            include=["id", "order_number", "total_amount"],
            read_only=["order_number"]
        )

        # 2. Filtering
        filtering = GraphQLMeta.Filtering(
            quick=["order_number", "contact_email"],
            presets={
                "high_value": {"total_amount": {"gte": 1000}}
            },
            custom={
                "overdue": "filter_overdue" # Reference to a staticmethod
            }
        )

        # 3. Computed Filters (Django Expressions)
        computed_filters = {
            "is_recent": {
                "expression": models.Q(placed_at__gte=Now() - timedelta(days=7)),
                "filter_type": "boolean"
            }
        }

        # 4. Access Control
        access = GraphQLMeta.AccessControl(
            operations={
                "retrieve": GraphQLMeta.OperationGuard(condition="can_access_order")
            },
            fields=[
                GraphQLMeta.FieldGuard(field="risk_score", roles=["admin"])
            ]
        )

        # 5. Resolvers
        resolvers = GraphQLMeta.Resolvers(
            queries={"priority_queue": "resolve_priority_queue"}
        )
```

## Detailed Options

### `Fields`
*   `include`: Explicit list of fields to expose.
*   `exclude`: Fields to hide.
*   `read_only`: Exposed in Queries, hidden in Mutation inputs.
*   `write_only`: Hidden in Queries, exposed in Mutation inputs.

### `Filtering`
*   `quick`: List of fields for the `quick` search argument.
*   `presets`: Map of named filters.
*   `custom`: Map of filter names to model methods.

### `AccessControl`
*   `operations`: Dict mapping `create`, `retrieve`, `update`, `delete` to `OperationGuard`.
*   `fields`: List of `FieldGuard` objects.

### `Resolvers`
*   `queries`: Custom root query fields for this model.
*   `mutations`: Custom mutations for this model.
*   `fields`: Custom field resolvers (e.g. `{"full_name": "resolve_full_name"}`).