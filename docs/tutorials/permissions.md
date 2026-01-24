# Permissions Tutorial

Learn how to implement granular access control in your GraphQL API.

## Overview of Security Layers

1. **Authentication**: Is the user logged in?
2. **Operation Guards**: Can they Create/Read/Update/Delete this specific model?
3. **Field Permissions**: Can they see or edit specific fields?
4. **Object-Level Permissions**: Do they own the specific record they are trying to access?

## Operation Guards

Restrict access to model operations in `GraphQLMeta`.

```python
class Product(models.Model):
    class GraphQLMeta:
        access = {
            "operations": {
                "create": {"roles": ["editor", "admin"]},
                "delete": {"roles": ["admin"]},
            }
        }
```

## Object-Level Security

Implement a "Can only view/edit my own data" policy using guards.

```python
class Order(models.Model):
    # ...
    class GraphQLMeta:
        access = {
            "operations": {
                "retrieve": {"condition": "is_owner_or_staff"}
            }
        }

    def is_owner_or_staff(self, user, operation, info):
        return self.customer.user == user or user.is_staff
```

## Field-Level Security

Protect sensitive fields from unauthorized roles.

```python
class Customer(models.Model):
    ssn = models.CharField(max_length=11)
    email = models.EmailField()

    class GraphQLMeta:
        field_permissions = {
            "ssn": {
                "roles": ["admin", "compliance"],
                "visibility": "hidden" # Not even in schema for others
            },
            "email": {
                "roles": ["support", "admin"],
                "visibility": "masked",
                "mask_value": "***@***.com"
            }
        }
```

## Defining Roles (RBAC)

You can define roles in a `meta.yaml` file in your app directory.

```yaml
# apps/store/meta.yaml
roles:
  manager:
    description: Can manage catalog and view reports
    permissions:
      - store.change_product
      - store.view_product
      - store.view_order
    parent_roles:
      - viewer
```

## Debugging Permissions

Use the `explainPermission` query to see why a user was allowed or denied access.

```graphql
query {
  explainPermission(permission: "store.change_product", objectId: "42") {
    allowed
    reason
    userRoles
  }
}
```

## Next Steps

- [Permissions Reference](../security/permissions.md)
- [Authentication Tutorial](./authentication.md)
- [Audit Logging](../extensions/audit-logging.md)
