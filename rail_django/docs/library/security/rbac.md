# RBAC System

> **Module Path:** `rail_django.security.rbac`

The Role-Based Access Control (RBAC) system provides flexible authorization through roles, permissions, and policy evaluation.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        RBAC System                               │
│                                                                 │
│  ┌─────────────────┐       ┌─────────────────┐                 │
│  │    Roles        │───────│   Permissions   │                 │
│  │  catalog_admin  │       │ store.add_prod  │                 │
│  │  catalog_viewer │       │ store.view_prod │                 │
│  └─────────────────┘       └─────────────────┘                 │
│           │                         │                           │
│           ▼                         ▼                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  Role Manager                            │   │
│  │  • Role registration                                     │   │
│  │  • Permission evaluation                                 │   │
│  │  • Context resolution                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  Policy Engine                           │   │
│  │  • Allow/Deny rules                                      │   │
│  │  • Priority-based evaluation                             │   │
│  │  • Field-level policies                                  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Core Concepts

### Roles

Roles are named permission bundles:

```python
from rail_django.security.rbac import RoleDefinition, role_manager

# Define a role
catalog_admin = RoleDefinition(
    name="catalog_admin",
    description="Full access to catalog management",
    permissions=[
        "store.view_product",
        "store.add_product",
        "store.change_product",
        "store.delete_product",
        "store.view_category",
        "store.add_category",
        "store.change_category"
    ],
    role_type="business",
    parent_roles=["catalog_viewer"]
)

# Register the role
role_manager.register_role(catalog_admin)
```

### Permissions

Permissions follow Django's naming convention:

```
app_label.action_model
```

Examples:
- `store.view_product` - View products
- `store.add_product` - Create products
- `store.change_product` - Update products
- `store.delete_product` - Delete products

### Wildcard Permissions

```python
# All permissions for an app
"store.*"

# All view permissions
"*.view_*"

# All permissions for a model
"store.*_product"
```

## Role Manager

### Register Roles

```python
from rail_django.security.rbac import role_manager, RoleDefinition

# From code
role_manager.register_role(RoleDefinition(
    name="order_manager",
    permissions=["store.view_order", "store.change_order"]
))

# From configuration
role_manager.load_roles_from_config({
    "order_manager": {
        "permissions": ["store.view_order", "store.change_order"],
        "parent_roles": ["order_viewer"]
    }
})
```

### Check Permissions

```python
from rail_django.security.rbac import role_manager

# Simple check
has_perm = role_manager.has_permission(user, "store.view_product")

# With context
from rail_django.security.rbac import PermissionContext

context = PermissionContext(
    user=request.user,
    object_instance=product,
    operation="update"
)
has_perm = role_manager.has_permission(user, "store.change_product", context)
```

### Get User Roles

```python
# Get all roles for a user
roles = role_manager.get_user_roles(user)

# Check if user has specific role
has_role = role_manager.user_has_role(user, "catalog_admin")
```

## Role Types

| Type | Description |
|------|-------------|
| `system` | Built-in roles (admin, superuser) |
| `functional` | Job function roles (developer, manager) |
| `business` | Business unit roles (sales, marketing) |
| `custom` | User-defined roles |

```python
RoleDefinition(
    name="finance_controller",
    role_type="functional",
    permissions=["finance.*"],
    is_system_role=False,
    max_users=5  # Limit users with this role
)
```

## Role Hierarchy

Roles can inherit from parent roles:

```python
# Child role inherits all permissions from parents
RoleDefinition(
    name="super_admin",
    parent_roles=["catalog_admin", "order_admin", "user_admin"],
    permissions=["admin.*"]  # Additional permissions
)
```

## Decorators

### require_role

```python
from rail_django.security.rbac import require_role

@require_role("admin")
def resolve_admin_data(root, info):
    return AdminData.objects.all()

@require_role(["admin", "manager"])  # Any of these roles
def resolve_management_data(root, info):
    return ManagementData.objects.all()
```

### require_permission

```python
from rail_django.security.rbac import require_permission

@require_permission("store.view_product")
def resolve_products(root, info):
    return Product.objects.all()

@require_permission(["store.view_product", "store.export_product"])
def resolve_export(root, info):
    return export_products()
```

### require_any_role / require_all_roles

```python
from rail_django.security.rbac import require_any_role, require_all_roles

@require_any_role(["admin", "manager"])  # User needs at least one
def resolve_data(root, info):
    pass

@require_all_roles(["finance", "senior"])  # User needs all
def resolve_sensitive_data(root, info):
    pass
```

## Contextual Permissions

For owner-based access (for example, `update_own`):

```python
from rail_django.security.rbac import PermissionContext, role_manager

def resolve_update_project(root, info, id, input):
    project = Project.objects.get(id=id)

    # Create context with object instance
    context = PermissionContext(
        user=info.context.user,
        object_instance=project
    )

    # Check contextual permission
    if not role_manager.has_permission(
        info.context.user,
        "projects.update_own",
        context
    ):
        raise GraphQLError("Cannot update this project")

    # Proceed with update
    ...
```

### Contextual Permission Suffixes

| Suffix | Description |
|--------|-------------|
| `_own` | User owns the object (`created_by == user`) |
| `_assigned` | User is assigned to object |
| `_team` | Object belongs to user's team |
| `_org` | Object belongs to user's organization |

## YAML Configuration

Define roles in `meta.yaml`:

```yaml
# apps/store/meta.yaml
roles:
  catalog_viewer:
    description: Read-only access to catalog
    role_type: functional
    permissions:
      - store.view_product
      - store.view_category

  catalog_editor:
    description: Can create and edit catalog items
    role_type: business
    permissions:
      - store.view_product
      - store.add_product
      - store.change_product
      - store.view_category
      - store.add_category
    parent_roles:
      - catalog_viewer

  catalog_admin:
    description: Full catalog control
    role_type: system
    permissions:
      - store.*
    parent_roles:
      - catalog_editor
    is_system_role: true
    max_users: 5
```

## GraphQLMeta Integration

Define access control per model:

```python
class Product(models.Model):
    class GraphQLMeta:
        access = GraphQLMetaConfig.Access(
            operations={
                "list": GraphQLMetaConfig.OperationAccess(
                    roles=["catalog_viewer", "catalog_editor", "catalog_admin"]
                ),
                "create": GraphQLMetaConfig.OperationAccess(
                    roles=["catalog_editor", "catalog_admin"],
                    permissions=["store.add_product"]
                ),
                "update": GraphQLMetaConfig.OperationAccess(
                    roles=["catalog_editor", "catalog_admin"],
                    guard="myapp.guards.can_update_product"
                ),
                "delete": GraphQLMetaConfig.OperationAccess(
                    roles=["catalog_admin"]
                )
            }
        )
```

## Custom Guards

Define custom authorization logic:

```python
# myapp/guards.py
def can_update_product(user, instance, context):
    """Check if user can update this product."""
    # Admins can update any product
    if user.groups.filter(name="catalog_admin").exists():
        return True

    # Editors can only update their own products
    if user.groups.filter(name="catalog_editor").exists():
        return instance.created_by_id == user.id

    return False

def can_delete_order(user, instance, context):
    """Check if user can delete this order."""
    # Can only delete draft orders
    if instance.status != "draft":
        return False

    # Must be owner or admin
    return instance.customer.user_id == user.id or user.is_staff
```

```python
class Order(models.Model):
    class GraphQLMeta:
        access = GraphQLMetaConfig.Access(
            operations={
                "delete": GraphQLMetaConfig.OperationAccess(
                    guard="myapp.guards.can_delete_order"
                )
            }
        )
```

## Permission Caching

Permissions are cached for performance:

```python
"security_settings": {
    "enable_permission_cache": True,
    "permission_cache_ttl_seconds": 300  # 5 minutes
}
```

Invalidate cache when permissions change:

```python
from rail_django.security.rbac import role_manager

# Invalidate for specific user
role_manager.invalidate_cache(user)

# Invalidate all
role_manager.clear_cache()
```

## Permission Auditing

Enable audit logging for permission checks:

```python
"security_settings": {
    "enable_permission_audit": True,
    "permission_audit_log_all": False,  # Only log denies
    "permission_audit_log_denies": True
}
```

Audit events include:
- User
- Permission checked
- Result (allow/deny)
- Context (model, instance, operation)

## API Reference

### RoleDefinition

```python
@dataclass
class RoleDefinition:
    name: str
    description: str = ""
    permissions: list[str] = field(default_factory=list)
    role_type: str = "custom"
    parent_roles: list[str] = field(default_factory=list)
    is_system_role: bool = False
    max_users: Optional[int] = None
```

### PermissionContext

```python
@dataclass
class PermissionContext:
    user: Any
    object_instance: Optional[Any] = None
    model: Optional[type] = None
    operation: Optional[str] = None
    field_name: Optional[str] = None
    extra: dict = field(default_factory=dict)
```

### RoleManager Methods

| Method | Description |
|--------|-------------|
| `register_role(role)` | Register a role definition |
| `get_role(name)` | Get role by name |
| `get_user_roles(user)` | Get all roles for user |
| `user_has_role(user, role)` | Check if user has role |
| `has_permission(user, perm, ctx)` | Check permission |
| `get_user_permissions(user)` | Get all permissions |
| `invalidate_cache(user)` | Clear permission cache |

## Examples

### Complete RBAC Setup

```python
# roles.py
from rail_django.security.rbac import RoleDefinition, role_manager

# Define role hierarchy
roles = [
    RoleDefinition(
        name="viewer",
        permissions=["*.view_*"]
    ),
    RoleDefinition(
        name="editor",
        permissions=["*.add_*", "*.change_*"],
        parent_roles=["viewer"]
    ),
    RoleDefinition(
        name="admin",
        permissions=["*.*"],
        parent_roles=["editor"],
        is_system_role=True
    )
]

# Register all roles
for role in roles:
    role_manager.register_role(role)
```

```python
# In app ready()
class MyAppConfig(AppConfig):
    def ready(self):
        from . import roles  # Load roles on startup
```

### Dynamic Role Assignment

```python
from django.contrib.auth.models import Group

def assign_role(user, role_name):
    """Assign a role to a user via Django groups."""
    group, _ = Group.objects.get_or_create(name=role_name)
    user.groups.add(group)

def remove_role(user, role_name):
    """Remove a role from a user."""
    try:
        group = Group.objects.get(name=role_name)
        user.groups.remove(group)
    except Group.DoesNotExist:
        pass
```

## Related Modules

- [Field Permissions](../../security/permissions.md) - Field-level access
- [Policies](../../reference/security.md) - Allow/deny rules
- [Audit](../../extensions/audit-logging.md) - Permission auditing
- [GraphQLMeta](../core/graphql-meta.md) - Per-model configuration
