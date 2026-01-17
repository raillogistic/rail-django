# Permissions & RBAC

## Overview

Rail Django offers a granular permission system combining RBAC (Role-Based Access Control), field-level permissions, and a policy engine. This guide covers the complete configuration and usage of these features.

---

## Table of Contents

1. [Basic Concepts](#basic-concepts)
2. [Configuration](#configuration)
3. [Role-Based Access Control (RBAC)](#role-based-access-control-rbac)
4. [Field Permissions](#field-permissions)
5. [Policy Engine](#policy-engine)
6. [GraphQLMeta - Per-Model Configuration](#graphqlmeta---per-model-configuration)
7. [Defining Roles via meta.yaml](#defining-roles-via-metayaml)
8. [GraphQL API](#graphql-api)
9. [Complete Examples](#complete-examples)
10. [Best Practices](#best-practices)

---

## Basic Concepts

### Permission Hierarchy

```
Level                 Description
─────────────────────────────────────────────────────────
Operation             create, read, update, delete (CRUD)
Model                 Access to the entire GraphQL Type
Field                 Access/visibility per field
Object                Contextual access (owner, assigned)
```

### Visibility Types

| Value      | Behavior                               |
| ---------- | -------------------------------------- |
| `visible`  | Field accessible normally              |
| `masked`   | Value partially hidden (`***@***.com`) |
| `hidden`   | Field not visible (null or error)      |
| `redacted` | Field visible but content replaced     |

---

## Configuration

### Global Settings

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        # Enables authentication checks
        "enable_authentication": True,
        # Enables authorization checks
        "enable_authorization": True,
        # Enables the allow/deny policy engine
        "enable_policy_engine": True,
        # Caches permission results
        "enable_permission_cache": True,
        "permission_cache_ttl_seconds": 300,
        # Audit of permission checks
        "enable_permission_audit": False,
        "permission_audit_log_denies": True,
        # Field-level permissions
        "enable_field_permissions": True,
        # Handling mode for unauthorized inputs
        "field_permission_input_mode": "reject",  # or "strip"
        # Object-level permissions
        "enable_object_permissions": True,
    },
    "query_settings": {
        # Requires Django permissions for queries
        "require_model_permissions": True,
        "model_permission_codename": "view",
    },
    "mutation_settings": {
        # Requires Django permissions for mutations
        "require_model_permissions": True,
        "model_permission_codenames": {
            "create": "add",
            "update": "change",
            "delete": "delete",
        },
    },
    "middleware_settings": {
        # Field permission middleware
        "enable_field_permission_middleware": True,
    },
}
```

---

## Role-Based Access Control (RBAC)

### Defining Roles in Code

```python
from rail_django.security import role_manager, RoleDefinition

# Define a simple role
role_manager.register_role(
    RoleDefinition(
        name="catalog_viewer",
        description="Read-only access to the catalog",
        permissions=[
            "store.view_product",
            "store.view_category",
        ],
    )
)

# Define a role with inheritance
role_manager.register_role(
    RoleDefinition(
        name="catalog_editor",
        description="Create and modify catalog",
        permissions=[
            "store.add_product",
            "store.change_product",
        ],
        parent_roles=["catalog_viewer"],  # Inherits permissions
    )
)

# System role with limits
role_manager.register_role(
    RoleDefinition(
        name="catalog_admin",
        description="Complete catalog administration",
        permissions=["store.*"],  # Wildcard
        parent_roles=["catalog_editor"],
        is_system_role=True,
        max_users=5,  # Limits number of users
    )
)
```

### @require_role Decorator

Protects resolvers and functions with role checks:

```python
from rail_django.security import require_role

@require_role("manager")
def resolve_financial_report(root, info):
    """
    Generates a financial report.
    Accessible only to managers.
    """
    return generate_report()

@require_role(["admin", "support"])  # OR logic
def resolve_sensitive_data(root, info):
    """Accessible to admins OR support."""
    return get_sensitive_data()
```

### Contextual Permissions

For object-based permissions (`*_own`, `*_assigned`):

```python
from rail_django.security import PermissionContext, role_manager

def resolve_update_project(root, info, project_id, input):
    project = Project.objects.get(pk=project_id)

    # Create a context with the instance
    context = PermissionContext(
        user=info.context.user,
        object_instance=project
    )

    # Check contextual permission
    if not role_manager.has_permission(
        info.context.user,
        "project.update_own",
        context
    ):
        raise PermissionError("You can only modify your own projects")

    # ... update logic
```

---

## Field Permissions

### Configuration in GraphQLMeta

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Customer(models.Model):
    """
    Customer Model with field permissions.

    Attributes:
        name: Customer name.
        email: Email (masked for non-support).
        phone: Phone (hidden for basic users).
        internal_notes: Internal notes (admin only).
    """
    name = models.CharField("Name", max_length=200)
    email = models.EmailField("Email")
    phone = models.CharField("Phone", max_length=20)
    internal_notes = models.TextField("Internal Notes", blank=True)

    class GraphQLMeta(GraphQLMetaConfig):
        field_permissions = {
            "email": {
                "roles": ["support", "admin"],
                "visibility": "masked",
                "mask_value": "***@***.com",
                "access": "read",  # read, write, or both
            },
            "phone": {
                "roles": ["support", "admin"],
                "visibility": "hidden",  # Returns null
            },
            "internal_notes": {
                "roles": ["admin"],
                "visibility": "hidden",
                "access": "both",  # Read and write
            },
        }
```

### Behavior by Role

| Field            | Basic User    | Support    | Admin      |
| ---------------- | ------------- | ---------- | ---------- |
| `name`           | ✅ Visible    | ✅ Visible | ✅ Visible |
| `email`          | `***@***.com` | ✅ Visible | ✅ Visible |
| `phone`          | `null`        | ✅ Visible | ✅ Visible |
| `internal_notes` | `null`        | `null`     | ✅ Visible |

### Input Handling Mode

Controls behavior when attempting to write to unauthorized fields:

```python
"security_settings": {
    # "reject": Refuses the mutation with an error
    # "strip": Silently ignores unauthorized fields
    "field_permission_input_mode": "reject",
}
```

---

## Policy Engine

The policy engine allows defining explicit access rules with priorities.

### Creating Policies

```python
from rail_django.security import (
    AccessPolicy, PolicyEffect, policy_manager
)

# DENY policy with high priority
policy_manager.register_policy(
    AccessPolicy(
        name="deny_tokens_for_contractors",
        effect=PolicyEffect.DENY,
        priority=50,  # Higher = more priority
        roles=["contractor"],
        fields=["*token*", "*secret*"],  # Pattern matching
        operations=["read", "write"],
        reason="Contractors cannot access tokens",
    )
)

# Specific ALLOW policy
policy_manager.register_policy(
    AccessPolicy(
        name="allow_own_profile",
        effect=PolicyEffect.ALLOW,
        priority=40,
        roles=["*"],  # All roles
        models=["auth.User"],
        operations=["read", "update"],
        conditions={"owner_field": "id"},  # Checks if it's their own profile
    )
)
```

### Conflict Resolution

1. Policies are sorted by priority (descending).
2. At equal priority, **DENY takes precedence over ALLOW**.
3. First matching policy determines the result.

### Explain Permission Query

Debug permission decisions via GraphQL:

```graphql
query ExplainPermission {
  explain_permission(
    permission: "project.update_own"
    model_name: "store.Product"
    object_id: "123"
  ) {
    allowed
    reason
    policy_decision {
      name
      effect
      priority
      reason
    }
  }
}
```

**Response:**

```json
{
  "data": {
    "explain_permission": {
      "allowed": true,
      "reason": "Allowed by policy 'allow_own_profile'",
      "policy_decision": {
        "name": "allow_own_profile",
        "effect": "ALLOW",
        "priority": 40,
        "reason": "User is owner of the object"
      }
    }
  }
}
```

---

## GraphQLMeta - Per-Model Configuration

### Complete Structure

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Order(models.Model):
    """
    Order Model with complete GraphQL configuration.
    """
    reference = models.CharField("Reference", max_length=50)
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE)
    status = models.CharField("Status", max_length=20)
    total = models.DecimalField("Total", max_digits=10, decimal_places=2)
    internal_notes = models.TextField("Internal Notes", blank=True)

    class GraphQLMeta(GraphQLMetaConfig):
        # ─── Field Configuration ───
        fields = GraphQLMetaConfig.Fields(
            exclude=["internal_notes"],  # Never exposed
            read_only=["reference", "created_at"],  # Not modifiable
        )

        # ─── Filtering ───
        filtering = GraphQLMetaConfig.Filtering(
            quick=["reference", "customer__name"],  # Quick search
            fields={
                "status": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "in"],
                    choices=["draft", "pending", "completed"],
                ),
                "total": GraphQLMetaConfig.FilterField(
                    lookups=["gt", "lt", "range"],
                ),
                "created_at": GraphQLMetaConfig.FilterField(
                    lookups=["gte", "lte", "date"],
                ),
            },
        )

        # ─── Sorting ───
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["reference", "total", "created_at"],
            default=["-created_at"],
        )

        # ─── Permissions by Operation ───
        access = GraphQLMetaConfig.Access(
            operations={
                "list": {"roles": ["sales", "admin"]},
                "retrieve": {"roles": ["sales", "admin"]},
                "create": {"roles": ["sales", "admin"]},
                "update": {"roles": ["admin"]},
                "delete": {"roles": ["admin"]},
            }
        )

        # ─── Field Permissions ───
        field_permissions = {
            "total": {
                "roles": ["accounting", "admin"],
                "visibility": "visible",
                "access": "read",
            },
        }

        # ─── Classifications (GDPR, PII) ───
        classifications = GraphQLMetaConfig.Classification(
            model=["financial"],
            fields={
                "total": ["financial", "sensitive"],
            },
        )
```

---

## Defining Roles via meta.yaml

Define roles and GraphQL configurations per application in a YAML file:

### File Structure

```yaml
# apps/store/meta.yaml
roles:
  catalog_viewer:
    description: Read-only access to the catalog.
    role_type: functional
    permissions:
      - store.view_product
      - store.view_category
  catalog_editor:
    description: Create and modify catalog.
    role_type: business
    permissions:
      - store.view_product
      - store.add_product
      - store.change_product
    parent_roles:
      - catalog_viewer
  catalog_admin:
    description: Complete catalog administration.
    role_type: system
    permissions:
      - store.*
    parent_roles:
      - catalog_editor
    is_system_role: true
    max_users: 5
models:
  Product:
    fields:
      exclude:
        - internal_notes
      read_only:
        - sku
    filtering:
      quick:
        - name
        - category__name
      fields:
        status:
          lookups:
            - exact
            - in
          choices:
            - draft
            - active
        price:
          - gt
          - lt
          - range
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
            - catalog_admin
```

### Important Notes

- Place the file at the application root (`apps/store/meta.yaml`).
- The loader runs at startup; restart the server to apply changes.
- Roles are additive and don't replace system roles.
- If a model defines `GraphQLMeta` in code, it takes priority over file-based meta.

---

## GraphQL API

### My Permissions

```graphql
query MyPermissions {
  my_permissions {
    permissions # List of Django permissions
    roles # List of assigned roles
    is_superuser
    is_staff
  }
}
```

### Check a Permission

```graphql
query CheckPermission {
  has_permission(permission: "store.change_product", object_id: "123") {
    allowed
    reason
  }
}
```

---

## Complete Examples

### Content Management System

```python
class Article(models.Model):
    """
    Article Model with publication workflow.
    """
    title = models.CharField("Title", max_length=200)
    content = models.TextField("Content")
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField("Status", max_length=20, default="draft")

    class GraphQLMeta:
        # Only authors and editors can see drafts
        access = {
            "operations": {
                "list": {
                    "roles": ["*"],  # Everyone
                    "conditions": [
                        # Automatically adds a filter
                        {"or": [
                            {"status": "published"},
                            {"author": "current_user"},
                        ]}
                    ],
                },
                "update": {
                    "roles": ["editor"],
                    # OR author can modify their own articles
                    "object_permission": "author",
                },
            },
        }

        field_permissions = {
            "content": {
                "roles": ["editor", "author"],
                "visibility": "hidden",
                "access": "write",
            },
        }
```

### Multi-Tenant API

```python
class Project(TenantMixin, models.Model):
    """
    Project with tenant isolation.
    """
    name = models.CharField("Name", max_length=100)
    budget = models.DecimalField("Budget", max_digits=12, decimal_places=2)

    class GraphQLMeta:
        # The tenant field is automatically filtered
        tenant_field = "organization"

        # Additional permissions by role within tenant
        access = {
            "operations": {
                "update": {"roles": ["project_manager", "org_admin"]},
            },
        }

        field_permissions = {
            "budget": {
                "roles": ["finance", "org_admin"],
                "visibility": "masked",
                "mask_value": "****",
            },
        }
```

---

## Best Practices

### 1. Principle of Least Privilege

```python
# ✅ Define granular roles
RoleDefinition(
    name="order_viewer",
    permissions=["store.view_order"],
)

RoleDefinition(
    name="order_processor",
    permissions=["store.view_order", "store.change_order"],
    parent_roles=["order_viewer"],
)

# ❌ Avoid overly broad roles
RoleDefinition(
    name="super_user",
    permissions=["*"],  # Dangerous
)
```

### 2. Permission Audit

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_permission_audit": True,
        "permission_audit_log_denies": True,
        "permission_audit_log_all": False,  # True in dev only
    },
}
```

### 3. Permission Tests

```python
from django.test import TestCase
from rail_django.security import role_manager

class PermissionTests(TestCase):
    def test_catalog_viewer_cannot_edit(self):
        user = User.objects.create_user("test")
        role_manager.assign_role(user, "catalog_viewer")

        self.assertTrue(
            role_manager.has_permission(user, "store.view_product")
        )
        self.assertFalse(
            role_manager.has_permission(user, "store.change_product")
        )
```

### 4. Role Documentation

Clearly document roles and their permissions in your `meta.yaml`:

```json
{
  "roles": {
    "support_level_1": {
      "description": "Level 1 support: Read tickets and customers.",
      "role_type": "functional",
      "permissions": ["support.view_ticket", "crm.view_customer"]
    }
  }
}
```

---

## See Also

- [JWT Authentication](./authentication.md)
- [Multi-Factor Authentication](./mfa.md)
- [Audit & Logging](../extensions/audit.md)
- [Complete Configuration](../graphql/configuration.md)
