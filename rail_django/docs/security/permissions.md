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

## Global Configuration

### Global Authentication
By default, Rail Django allows anonymous access if the underlying Django view does not restrict it. You can enforce authentication globally across your entire GraphQL schema:

```python
# settings.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "authentication_required": True, # Blocks all anonymous queries/mutations
    },
    "security_settings": {
        "enable_authorization": True,
        "enable_field_permissions": True,
        "enable_policy_engine": True,
    },
}
```

## Role-Based Access Control (RBAC)

RBAC allows you to group permissions into logical roles like `admin`, `editor`, and `viewer`.

### Defining Roles
Define your hierarchy in an initialization module (e.g., `apps.py` or a dedicated `security.py`):

```python
from rail_django.security import role_manager, RoleDefinition

# 1. Base Viewer: Can only see public data
role_manager.register_role(
    RoleDefinition(
        name="viewer",
        description="Read-only access to public data",
        permissions=["cms.view_article", "auth.view_user"]
    )
)

# 2. Editor: Inherits from Viewer + can modify content
role_manager.register_role(
    RoleDefinition(
        name="editor",
        description="Can create and edit articles",
        permissions=["cms.add_article", "cms.change_article"],
        parent_roles=["viewer"]
    )
)

# 3. Admin: Full control
role_manager.register_role(
    RoleDefinition(
        name="admin",
        description="System administrator",
        permissions=["*"], # Wildcard for all permissions
        parent_roles=["editor"]
    )
)
```

## Per-Model Security (GraphQLMeta)

The `GraphQLMeta` class on your models is the primary way to enforce security rules.

### Operation Guards & Field Security
The following example demonstrates a `Profile` model with different rules for **Admins** and **Standard Users**.

```python
from django.db import models

class Profile(models.Model):
    user = models.OneToOneField("auth.User", on_delete=models.CASCADE)
    full_name = models.CharField(max_length=255)
    salary = models.DecimalField(max_digits=10, decimal_places=2)
    ssn = models.CharField(max_length=11)
    is_verified = models.BooleanField(default=False)

    class GraphQLMeta:
        # Operation Guards: Who can do what?
        access = {
            "operations": {
                "list": {"roles": ["viewer", "editor", "admin"]},
                "create": {"roles": ["admin"]}, # Only Admins create profiles
                "update": {
                    "roles": ["editor", "admin"],
                    "condition": "is_owner_or_admin" # Custom logic
                },
                "delete": {"roles": ["admin"]} # Only Admins delete
            }
        }

        # Field-Level Security: Sensitive data masking
        field_permissions = {
            "salary": {
                "roles": ["admin"], # Only Admins see exact salary
                "visibility": "hidden" # Everyone else sees null
            },
            "ssn": {
                "roles": ["admin"],
                "visibility": "masked",
                "mask_value": "***-**-XXXX" # Editors see masked version
            }
        }

    def is_owner_or_admin(self, user, operation, info):
        """Row-Level Security (RLS) Logic"""
        if user.is_superuser or "admin" in user.roles:
            return True
        return self.user == user
```

### Row-Level Security (RLS)
While Operation Guards control *if* an action can be taken, RLS controls *which* rows are returned.

#### Using `get_queryset` for Automatic Filtering
You can restrict the list of objects a user sees by overriding `get_queryset` logic via the policy engine or model managers:

```python
# Policy-based RLS
from rail_django.security import AccessPolicy, PolicyEffect, policy_manager

policy_manager.register_policy(
    AccessPolicy(
        name="users_only_see_own_profiles",
        effect=PolicyEffect.ALLOW,
        roles=["viewer"],
        # Dynamic filter injected into the database query
        row_filter=lambda user: {"user": user} if not user.is_staff else {}
    )
)
```

## User vs Admin Narrative

| Feature | Standard User (`viewer`) | Administrator (`admin`) |
|---------|---------------------------|-------------------------|
| **List Profiles** | Sees only their own profile (RLS). | Sees all profiles in the system. |
| **View `salary`** | Field is `null` (Hidden). | Sees actual decimal value. |
| **View `ssn`** | Sees `***-**-XXXX` (Masked). | Sees actual social security number. |
| **Delete Profile** | Operation Blocked (403). | Allowed to delete any profile. |
| **Update Verification**| Operation Blocked. | Allowed to verify users. |

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
