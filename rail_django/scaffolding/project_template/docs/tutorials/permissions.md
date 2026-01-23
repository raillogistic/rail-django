# Permissions Tutorial

This tutorial covers implementing role-based access control (RBAC), field-level permissions, and operation guards in your Rail Django API.

## Overview

Rail Django provides multiple layers of access control:

```
┌─────────────────────────────────────────────────────────┐
│                  Permission Layers                       │
│                                                         │
│  1. Authentication    → Is user logged in?              │
│  2. Model Permissions → Can user access this model?     │
│  3. Operation Guards  → Can user perform this action?   │
│  4. Field Permissions → Can user see/edit this field?   │
│  5. Object Permissions→ Can user access this instance?  │
└─────────────────────────────────────────────────────────┘
```

---

## Step 1: Define Roles

### Using Django Groups

The simplest approach - use Django's built-in groups as roles:

```python
# Create groups in Django admin or via code
from django.contrib.auth.models import Group, Permission

# Create roles
viewer = Group.objects.create(name="viewer")
editor = Group.objects.create(name="editor")
admin = Group.objects.create(name="admin")

# Assign permissions to roles
from django.contrib.contenttypes.models import ContentType
from apps.store.models import Product

content_type = ContentType.objects.get_for_model(Product)
view_perm = Permission.objects.get(codename="view_product", content_type=content_type)
add_perm = Permission.objects.get(codename="add_product", content_type=content_type)
change_perm = Permission.objects.get(codename="change_product", content_type=content_type)
delete_perm = Permission.objects.get(codename="delete_product", content_type=content_type)

# Viewer can only view
viewer.permissions.add(view_perm)

# Editor can view, add, change
editor.permissions.add(view_perm, add_perm, change_perm)

# Admin can do everything
admin.permissions.add(view_perm, add_perm, change_perm, delete_perm)
```

### Using meta.yaml

Define roles in your app's `meta.yaml`:

```yaml
# apps/store/meta.yaml
roles:
  catalog_viewer:
    description: Read-only access to products and categories
    permissions:
      - store.view_product
      - store.view_category

  catalog_editor:
    description: Can create and modify products
    permissions:
      - store.view_product
      - store.add_product
      - store.change_product
      - store.view_category
      - store.add_category
      - store.change_category
    parent_roles:
      - catalog_viewer

  catalog_admin:
    description: Full control over catalog
    permissions:
      - store.*
    parent_roles:
      - catalog_editor
    is_system_role: true
```

### Using Code

```python
# apps/store/roles.py
from rail_django.security.rbac import RoleDefinition, role_manager

roles = [
    RoleDefinition(
        name="catalog_viewer",
        description="Read-only catalog access",
        permissions=["store.view_product", "store.view_category"]
    ),
    RoleDefinition(
        name="catalog_editor",
        description="Create and edit catalog items",
        permissions=[
            "store.view_product",
            "store.add_product",
            "store.change_product"
        ],
        parent_roles=["catalog_viewer"]
    ),
    RoleDefinition(
        name="catalog_admin",
        description="Full catalog control",
        permissions=["store.*"],
        parent_roles=["catalog_editor"],
        is_system_role=True
    )
]

def register_roles():
    for role in roles:
        role_manager.register_role(role)

# apps/store/apps.py
class StoreConfig(AppConfig):
    def ready(self):
        from .roles import register_roles
        register_roles()
```

---

## Step 2: Assign Roles to Users

### Via Django Admin

1. Go to Django Admin
2. Edit a User
3. Add them to Groups (roles)

### Via Code

```python
from django.contrib.auth.models import Group

def assign_role(user, role_name):
    group, _ = Group.objects.get_or_create(name=role_name)
    user.groups.add(group)

def remove_role(user, role_name):
    try:
        group = Group.objects.get(name=role_name)
        user.groups.remove(group)
    except Group.DoesNotExist:
        pass

# Usage
assign_role(user, "catalog_editor")
```

### Via GraphQL Mutation

```graphql
mutation {
  assignRole(userId: "5", role: "catalog_editor") {
    ok
    user {
      groups {
        name
      }
    }
  }
}
```

---

## Step 3: Configure Model Permissions

### Auto-Generated Permissions

Enable Django permission checks:

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        "require_model_permissions": True,
        "model_permission_codename": "view"  # Requires store.view_product
    },
    "mutation_settings": {
        "require_model_permissions": True,
        "model_permission_codenames": {
            "create": "add",     # Requires store.add_product
            "update": "change",  # Requires store.change_product
            "delete": "delete"   # Requires store.delete_product
        }
    }
}
```

### Operation Guards

Define custom access rules in GraphQLMeta:

```python
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Product(models.Model):
    class GraphQLMeta(GraphQLMetaConfig):
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
                    guard="apps.store.guards.can_update_product"
                ),
                "delete": GraphQLMetaConfig.OperationAccess(
                    roles=["catalog_admin"]
                )
            }
        )
```

### Custom Guards

```python
# apps/store/guards.py

def can_update_product(user, instance, context):
    """Check if user can update this product."""
    # Admins can update anything
    if user.groups.filter(name="catalog_admin").exists():
        return True

    # Editors can only update products in their categories
    if user.groups.filter(name="catalog_editor").exists():
        user_categories = user.profile.managed_categories.all()
        return instance.category in user_categories

    return False


def can_delete_order(user, instance, context):
    """Check if user can delete this order."""
    # Only allow deleting draft orders
    if instance.status != "draft":
        return False

    # User must own the order or be admin
    if instance.customer.user == user:
        return True

    return user.groups.filter(name="order_admin").exists()
```

---

## Step 4: Field-Level Permissions

Control which fields users can see or modify:

```python
class Customer(models.Model):
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    salary = models.DecimalField(max_digits=10, decimal_places=2)
    social_security = models.CharField(max_length=11)
    internal_notes = models.TextField()

    class GraphQLMeta(GraphQLMetaConfig):
        access = GraphQLMetaConfig.Access(
            fields=[
                # Salary: Only HR can see
                GraphQLMetaConfig.FieldAccess(
                    field="salary",
                    access="none",
                    visibility="hidden",
                    roles=["hr_admin"]
                ),

                # SSN: Hidden from most, visible to compliance
                GraphQLMetaConfig.FieldAccess(
                    field="social_security",
                    access="read",
                    visibility="hidden",
                    roles=["compliance_officer"]
                ),

                # Email: Masked for support, full for managers
                GraphQLMetaConfig.FieldAccess(
                    field="email",
                    access="read",
                    visibility="masked",
                    mask_value="***@***.***",
                    roles=["support", "manager"]
                ),

                # Internal notes: Only staff can see/edit
                GraphQLMetaConfig.FieldAccess(
                    field="internal_notes",
                    access="write",
                    visibility="visible",
                    roles=["staff"]
                )
            ]
        )
```

### Visibility Options

| Visibility | Description |
|------------|-------------|
| `visible` | Field shown normally |
| `masked` | Field shown with masked value |
| `hidden` | Field completely hidden (not in response) |

### Access Options

| Access | Description |
|--------|-------------|
| `read` | Can read but not write |
| `write` | Can read and write |
| `none` | Cannot access at all |

---

## Step 5: Object-Level Permissions

Check permissions on specific instances:

### Owner-Based Access

```python
class Project(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    team = models.ManyToManyField(User, related_name="team_projects")

    class GraphQLMeta(GraphQLMetaConfig):
        access = GraphQLMetaConfig.Access(
            operations={
                "update": GraphQLMetaConfig.OperationAccess(
                    guard="apps.projects.guards.can_update_project"
                ),
                "delete": GraphQLMetaConfig.OperationAccess(
                    guard="apps.projects.guards.can_delete_project"
                )
            }
        )

# apps/projects/guards.py
def can_update_project(user, project, context):
    """Owner and team members can update."""
    if project.owner == user:
        return True
    if project.team.filter(id=user.id).exists():
        return True
    return user.is_staff

def can_delete_project(user, project, context):
    """Only owner can delete."""
    return project.owner == user or user.is_superuser
```

### Contextual Permissions

```python
from rail_django.security.rbac import PermissionContext, role_manager

def resolve_update_project(root, info, id, input):
    project = Project.objects.get(id=id)

    # Create context with instance
    context = PermissionContext(
        user=info.context.user,
        object_instance=project,
        operation="update"
    )

    # Check contextual permission
    if not role_manager.has_permission(
        info.context.user,
        "projects.update_own",
        context
    ):
        raise GraphQLError("Cannot update this project")

    # Continue with update...
```

---

## Step 6: Test Your Permissions

### In GraphQL

Query as different users to verify access:

```graphql
# As viewer - should see products
query {
  products { id name price }
}

# As viewer - should fail
mutation {
  createProduct(input: { name: "Test", price: 10 }) {
    ok
    errors { message }
  }
}
# Error: "Permission required: store.add_product"

# As editor - should work
mutation {
  createProduct(input: { name: "Test", price: 10 }) {
    ok
    product { id }
  }
}
```

### Using Explain Query

Debug permission decisions:

```graphql
query {
  explainPermission(
    permission: "store.change_product"
    modelName: "store.Product"
    objectId: "123"
  ) {
    allowed
    reason
    userRoles
    requiredRoles
    policyDecision {
      name
      effect
      priority
    }
  }
}
```

### Unit Tests

```python
from django.test import TestCase
from django.contrib.auth.models import Group, User
from rail_django.testing import RailGraphQLTestClient

class PermissionTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user("viewer", "v@test.com", "pass")
        self.editor = User.objects.create_user("editor", "e@test.com", "pass")

        viewer_group = Group.objects.create(name="catalog_viewer")
        editor_group = Group.objects.create(name="catalog_editor")

        self.viewer.groups.add(viewer_group)
        self.editor.groups.add(editor_group)

        self.client = RailGraphQLTestClient()

    def test_viewer_cannot_create(self):
        result = self.client.execute(
            """
            mutation {
              createProduct(input: { name: "Test", price: 10 }) {
                ok
                errors { message }
              }
            }
            """,
            user=self.viewer
        )
        self.assertFalse(result["data"]["createProduct"]["ok"])

    def test_editor_can_create(self):
        result = self.client.execute(
            """
            mutation {
              createProduct(input: { name: "Test", price: 10 }) {
                ok
              }
            }
            """,
            user=self.editor
        )
        self.assertTrue(result["data"]["createProduct"]["ok"])
```

---

## Practical Examples

### E-commerce Roles

```yaml
# apps/store/meta.yaml
roles:
  customer:
    permissions:
      - store.view_product
      - store.view_category
      - store.add_order
      - store.view_order  # Own orders only

  sales_rep:
    permissions:
      - store.view_product
      - store.view_category
      - store.view_order
      - store.change_order
      - store.view_customer
    parent_roles:
      - customer

  inventory_manager:
    permissions:
      - store.view_product
      - store.change_product
      - store.add_product

  store_admin:
    permissions:
      - store.*
    is_system_role: true
```

### Multi-Tenant Permissions

```python
class Document(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()

    class GraphQLMeta(GraphQLMetaConfig):
        access = GraphQLMetaConfig.Access(
            operations={
                "list": GraphQLMetaConfig.OperationAccess(
                    guard="apps.docs.guards.filter_by_tenant"
                ),
                "update": GraphQLMetaConfig.OperationAccess(
                    guard="apps.docs.guards.can_update_document"
                )
            }
        )

# guards.py
def filter_by_tenant(user, queryset, context):
    """Filter documents to user's tenant."""
    return queryset.filter(tenant=user.profile.tenant)

def can_update_document(user, document, context):
    """Check tenant and ownership."""
    if document.tenant != user.profile.tenant:
        return False
    return document.owner == user or user.groups.filter(name="doc_admin").exists()
```

---

## Common Patterns

### Superuser Bypass

```python
def check_permission(user, permission, instance=None):
    # Superusers can do anything
    if user.is_superuser:
        return True

    # Regular permission check
    return user.has_perm(permission)
```

### Anonymous Access

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "authentication_required": False  # Allow anonymous
    }
}

class Product(models.Model):
    class GraphQLMeta(GraphQLMetaConfig):
        access = GraphQLMetaConfig.Access(
            operations={
                # Anonymous can view products
                "list": GraphQLMetaConfig.OperationAccess(
                    require_authentication=False
                ),
                # Must be authenticated to create
                "create": GraphQLMetaConfig.OperationAccess(
                    require_authentication=True,
                    roles=["editor"]
                )
            }
        )
```

### Hierarchical Roles

```python
# Define hierarchy
roles_hierarchy = {
    "admin": ["manager", "editor", "viewer"],
    "manager": ["editor", "viewer"],
    "editor": ["viewer"],
    "viewer": []
}

def user_has_role(user, required_role):
    user_roles = set(user.groups.values_list("name", flat=True))

    # Direct match
    if required_role in user_roles:
        return True

    # Check if user has a higher role
    for role in user_roles:
        if required_role in roles_hierarchy.get(role, []):
            return True

    return False
```

---

## Next Steps

- [Audit Logging](./audit-logging.md) - Track permission checks
- [Authentication](./authentication.md) - User identity
- [Configuration](./configuration.md) - All security settings
