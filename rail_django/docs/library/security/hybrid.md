# Hybrid RBAC + ABAC

`rail-django` can combine RBAC and ABAC in a single permission decision.
This behavior is controlled by `security_settings.hybrid_strategy`.

## Decision flow

Hybrid evaluation follows this order:

1. Evaluate policy engine rules first.
2. Evaluate RBAC permissions.
3. Evaluate ABAC policies when ABAC is enabled.
4. Combine RBAC and ABAC decisions by strategy.

Policy engine decisions keep top priority and can short-circuit the flow.

## Strategies

Use one of these strategy values:

- `rbac_and_abac`: both systems must allow.
- `rbac_or_abac`: either system can allow.
- `abac_override`: ABAC result is final.
- `rbac_then_abac`: RBAC must allow, then ABAC can deny.
- `most_restrictive`: most restrictive result wins.

## Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_abac": True,
        "hybrid_strategy": "rbac_then_abac",
    }
}
```

## Programmatic usage

Use `hybrid_engine` directly:

```python
from rail_django.security.hybrid import hybrid_engine
from rail_django.security.rbac import PermissionContext

context = PermissionContext(
    user=request.user,
    object_instance=document,
    operation="update",
    additional_context={"request": request},
)

decision = hybrid_engine.has_permission(
    request.user,
    "docs.change_document",
    context=context,
)

if not decision.allowed:
    raise PermissionDenied(decision.reason)
```

## Next steps

- [ABAC system](./abac.md)
- [RBAC system](./rbac.md)
- [Security reference](../../reference/security.md)

