# Permissions and RBAC

Rail Django combines Django permissions, RBAC role evaluation, field-level
access control, and policy evaluation.

This page describes the permission behavior available in the current security
and permissions extensions.

## Enable permission controls

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "authentication_required": True,
    },
    "query_settings": {
        "require_model_permissions": True,
        "model_permission_codename": "view",
    },
    "mutation_settings": {
        "require_model_permissions": True,
        "model_permission_codenames": {
            "create": "add",
            "update": "change",
            "delete": "delete",
        },
    },
    "security_settings": {
        "enable_authorization": True,
        "enable_field_permissions": True,
        "enable_policy_engine": True,
        "enable_permission_cache": True,
    },
}
```

## RBAC role management

Use `role_manager` to register role definitions and inherit permissions.

```python
from rail_django.security.rbac import role_manager, RoleDefinition

role_manager.register_role(
    RoleDefinition(
        name="catalog_editor",
        description="Can update product catalog",
        permissions=["store.change_product", "store.view_product"],
    )
)
```

## Policy rules

Use `policy_manager` for cross-cutting allow or deny logic.

```python
from rail_django.security import AccessPolicy, PolicyEffect, policy_manager

policy_manager.register_policy(
    AccessPolicy(
        name="deny_sensitive_for_contractors",
        effect=PolicyEffect.DENY,
        priority=100,
        roles=["contractor"],
        fields=["*token*", "*secret*"],
        reason="Contractor access is restricted for sensitive fields.",
    )
)
```

## Field-level access

Field-level decisions are handled by `field_permission_manager` in
`rail_django.security.field_permissions`. Visibility outcomes include normal
access, masking, and hidden behavior depending on policy and role context.

## Permission inspection queries

The permissions extension exposes runtime permission inspection.

```graphql
query MyPermissions {
  myPermissions {
    modelName
    canRead
    canCreate
    canUpdate
    canDelete
  }
}
```

Explain a permission decision:

```graphql
query Explain($permission: String!, $modelName: String) {
  explainPermission(permission: $permission, modelName: $modelName) {
    allowed
    reason
    roles
    effectivePermissions
    policyDecision { name effect priority reason }
  }
}
```

## Best practices

- Keep `authentication_required` enabled for production schemas.
- Prefer role assignment over direct user permission grants.
- Keep model and mutation permission checks enabled.
- Use policy rules for exceptional cases, not baseline access design.

## Next steps

Continue with [validation](./validation.md) and
[security reference](../reference/security.md).
