# Permissions & RBAC

Rail Django provides a granular and flexible permission system that combines standard Django permissions with Role-Based Access Control (RBAC), field-level security, and a powerful policy engine.

## Overview

The security system allows you to:
- Define **Roles** that group multiple permissions.
- Restrict access to **Models** and **Operations** (CRUD).
- Control **Field Visibility** (Visible, Masked, Hidden, Redacted) based on roles.
- Implement **Object-Level Permissions** (e.g., "users can only edit their own projects").
- Use a **Policy Engine** for complex allow/deny rules with priorities.
- Audit permission decisions.

## Basic Configuration

Enable the security features in your settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_authentication": True,
        "enable_authorization": True,
        "enable_field_permissions": True,
        "enable_policy_engine": True,
        "enable_object_permissions": True,
    },
}
```

## Role-Based Access Control (RBAC)

### Defining Roles
Roles can be defined in Python code or via a `meta.yaml` file in your apps.

```python
from rail_django.security import role_manager, RoleDefinition

role_manager.register_role(
    RoleDefinition(
        name="editor",
        description="Can edit catalog products",
        permissions=["store.change_product", "store.view_product"],
        parent_roles=["viewer"], # Inherits permissions
    )
)
```

### The @require_role Decorator
You can protect custom resolvers or functions:

```python
from rail_django.security import require_role

@require_role("manager")
def resolve_sensitive_report(root, info):
    return generate_report()
```

## Per-Model Configuration (GraphQLMeta)

Use `GraphQLMeta` on your models to define access rules.

```python
class Order(models.Model):
    class GraphQLMeta:
        # 1. Operation Guards
        access = {
            "operations": {
                "list": {"roles": ["sales", "admin"]},
                "update": {
                    "roles": ["admin"],
                    "condition": "can_modify_order" # Method on model
                }
            }
        }

        # 2. Field Permissions
        field_permissions = {
            "total_amount": {
                "roles": ["accounting", "admin"],
                "visibility": "masked",
                "mask_value": "****"
            },
            "internal_notes": {
                "roles": ["admin"],
                "visibility": "hidden"
            }
        }

    def can_modify_order(self, user, operation, info):
        return self.customer.user == user or user.is_staff
```

## Policy Engine

The policy engine allows for high-level rules that span multiple models or fields.

```python
from rail_django.security import AccessPolicy, PolicyEffect, policy_manager

policy_manager.register_policy(
    AccessPolicy(
        name="deny_sensitive_to_contractors",
        effect=PolicyEffect.DENY,
        priority=100,
        roles=["contractor"],
        fields=["*token*", "*secret*", "ssn"],
        reason="Contractors cannot access sensitive identity fields"
    )
)
```

Rules are evaluated by priority. If priorities are equal, **DENY** takes precedence over **ALLOW**.

## Field Visibility Types

| Type | Behavior |
|------|----------|
| `VISIBLE` | Field is accessible normally. |
| `MASKED` | Value is partially hidden (e.g., `***@***.com`). |
| `HIDDEN` | Field is not visible (returns `null` or error). |
| `REDACTED` | Content is completely replaced by a placeholder. |

## GraphQL API

Users can inspect their own permissions and roles:

```graphql
query MyPermissions {
  myPermissions {
    roles
    permissions
    isSuperuser
  }
}
```

Debug permission decisions:
```graphql
query Explain {
  explainPermission(permission: "store.change_product", objectId: "42") {
    allowed
    reason
  }
}
```

## Best Practices

1. **Principle of Least Privilege**: Start with no permissions and grant them explicitly.
2. **Use Roles**: Avoid assigning raw permissions to users; use roles for better management.
3. **Document Roles**: Use the `description` field in `RoleDefinition` to keep track of what roles are for.
4. **Test Permissions**: Write unit tests to ensure your security rules behave as expected.

## See Also

- [Authentication](./authentication.md)
- [Validation](./validation.md)
- [Audit Logging](../extensions/audit-logging.md)
