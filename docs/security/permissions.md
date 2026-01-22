# Permissions & RBAC

Rail Django provides granular control over who can access and modify your data.

## 1. Operation Guards

You can restrict access to entire operations (Create, Read, Update, Delete) in `GraphQLMeta`.

```python
class Order(models.Model):
    class GraphQLMeta:
        access = GraphQLMeta.AccessControl(
            operations={
                "retrieve": GraphQLMeta.OperationGuard(
                    condition="can_access_order",
                    deny_message="You do not have permission to view this order.",
                ),
                "update": GraphQLMeta.OperationGuard(
                    roles=["admin", "manager"], # Only specific roles
                    condition="can_modify_order"
                )
            }
        )

    @staticmethod
    def can_access_order(user, operation, info, instance, model):
        if user.is_staff:
            return True
        # Regular users can only see their own orders
        return instance.customer.user == user
```

## 2. Field-Level Permissions

Protect specific fields within a model.

```python
class Order(models.Model):
    class GraphQLMeta:
        access = GraphQLMeta.AccessControl(
            fields=[
                # Only users with 'view_financials' permission can see taxAmount
                GraphQLMeta.FieldGuard(
                    field="tax_amount", 
                    permissions=["store.view_financials"]
                ),
                # Mask sensitive fields instead of erroring
                GraphQLMeta.FieldGuard(
                    field="risk_score", 
                    roles=["security_analyst"],
                    mask_value=0
                )
            ]
        )
```

## 3. Role-Based Access Control (RBAC)

Manage permissions via roles.

### Defining Roles
```python
class Project(models.Model):
    class GraphQLMeta:
        access = GraphQLMeta.AccessControl(
            roles={
                "auditor": GraphQLMeta.Role(
                    name="auditor",
                    permissions=["view_financials", "view_audit_logs"]
                )
            }
        )
```

### Checking Roles in Code
```python
from rail_django.security.rbac import role_manager

def resolve_sensitive_report(root, info):
    if not role_manager.has_role(info.context.user, "auditor"):
        raise PermissionError("Auditors only.")
    return generate_report()
```

## 4. Custom Permission Classes

For reusable permission logic.

```python
from rail_django.core.permissions import BasePermission

class IsOwnerOrStaff(BasePermission):
    def has_object_permission(self, source, info, obj):
        user = info.context.user
        return user.is_staff or obj.customer.user == user

class Order(models.Model):
    class GraphQLMeta:
        permission_classes = [IsOwnerOrStaff]
```