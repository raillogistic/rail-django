# ABAC system

`rail-django` includes an Attribute-Based Access Control (ABAC) engine that
works with the existing RBAC and policy systems.

ABAC evaluates request context attributes in four categories:

- `subject`: user attributes like roles, department, and flags.
- `resource`: model and instance attributes.
- `environment`: request and runtime attributes.
- `action`: operation attributes like permission and operation type.

## Quick start

Use the ABAC manager to register policies and evaluate access:

```python
from rail_django.security.abac import (
    ABACPolicy,
    ConditionOperator,
    MatchCondition,
    abac_manager,
)

abac_manager.register_policy(
    ABACPolicy(
        name="department_isolation",
        effect="allow",
        priority=50,
        subject_conditions={
            "department": MatchCondition(
                ConditionOperator.EQ,
                target="resource.department",
            )
        },
    )
)
```

## Supported condition operators

ABAC supports these operators in `MatchCondition.operator`:

- `eq`, `neq`
- `in`, `not_in`
- `contains`, `starts_with`
- `gt`, `gte`, `lt`, `lte`, `between`
- `matches`
- `exists`
- `is_subset`, `intersects`
- `custom`

## Configuration

Configure ABAC in `security_settings`:

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_abac": True,
        "hybrid_strategy": "rbac_then_abac",
        "abac_default_effect": "deny",
        "abac_cache_ttl_seconds": 60,
        "abac_audit_decisions": False,
    }
}
```

## GraphQLMeta model policies

You can define model-scoped ABAC policies in `GraphQLMeta`:

```python
class Document(models.Model):
    department = models.CharField(max_length=100)

    class GraphQLMeta:
        abac_policies = [
            {
                "name": "department_isolation",
                "effect": "allow",
                "subject_conditions": {
                    "department": {
                        "operator": "eq",
                        "target": "resource.department",
                    }
                },
            }
        ]
```

`rail-django` namespaces these policies per model when it registers them.

## Resolver decorator

Use `require_attributes` for resolver-level checks:

```python
from rail_django.security.abac import require_attributes

@require_attributes(
    subject_conditions={"is_staff": {"operator": "eq", "value": True}}
)
def resolve_admin_data(root, info):
    ...
```

## Next steps

- [Hybrid RBAC + ABAC](./hybrid.md)
- [RBAC system](./rbac.md)
- [Security reference](../../reference/security.md)

