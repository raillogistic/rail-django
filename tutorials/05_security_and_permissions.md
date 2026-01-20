# Tutorial 5: Security & Permissions

Security is a first-class citizen in Rail Django. This tutorial covers Authentication, Role-Based Access Control (RBAC), and granular Field Permissions.

## 1. Authentication

Rail Django supports JWT (JSON Web Token) authentication out of the box.

### Configuration

Enable authentication in `settings.py`:

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_authentication": True,
        # If True, anonymous users are rejected globally
        "authentication_required": False, 
    }
}
```

### Obtaining a Token

Use the built-in `login` mutation:

```graphql
mutation {
  login(username: "admin", password: "password123") {
    token
    refreshToken
  }
}
```

Pass the token in the header of subsequent requests:
`Authorization: Bearer <your_token>`

## 2. Access Control (Permissions)

You can control access at three levels: **Model**, **Operation**, and **Field**.

### Model/Operation Level

Use `GraphQLMeta.AccessControl` to define who can perform operations (`list`, `create`, `update`, `delete`).

```python
from rail_django.models import GraphQLMetaConfig

class Report(models.Model):
    # ...

    class GraphQLMeta(GraphQLMetaConfig):
        access = GraphQLMetaConfig.AccessControl(
            operations={
                # Only "admins" can delete
                "delete": GraphQLMetaConfig.OperationGuard(roles=["admin"]),
                
                # Only users with specific permission can create
                "create": GraphQLMetaConfig.OperationGuard(permissions=["myapp.add_report"]),
                
                # Custom logic for updates
                "update": GraphQLMetaConfig.OperationGuard(
                    condition="can_edit_report"
                ),
                
                # Public read access
                "list": GraphQLMetaConfig.OperationGuard(allow_anonymous=True),
                "retrieve": GraphQLMetaConfig.OperationGuard(allow_anonymous=True),
            }
        )
    
    @staticmethod
    def can_edit_report(user, operation, info, instance, model):
        # Only owner can edit
        return instance.owner == user
```

### Field Level

Control visibility of specific fields based on roles or conditions.

```python
class User(models.Model):
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    is_verified = models.BooleanField()

    class GraphQLMeta(GraphQLMetaConfig):
        access = GraphQLMetaConfig.AccessControl(
            fields=[
                # Hide phone number from everyone except admins
                GraphQLMetaConfig.FieldGuard(
                    field="phone",
                    visibility="hidden",
                    roles=["admin"] 
                ),
                # Mask email for non-owners (e.g. j***@gmail.com)
                GraphQLMetaConfig.FieldGuard(
                    field="email",
                    visibility="masked",
                    condition="is_owner_or_admin"
                )
            ]
        )
```

## 3. Input Validation

Rail Django includes a sanitization engine to prevent XSS and Injection attacks.

**Settings:**
```python
"security_settings": {
    "enable_input_validation": True,
    "input_allow_html": False, # Strip HTML tags
    "enable_sql_injection_protection": True,
}
```

If a user tries to submit `<script>alert(1)</script>`, the mutation will be rejected (or sanitized, depending on config).

## 4. Rate Limiting

Protect your API from abuse.

```python
RAIL_DJANGO_RATE_LIMITING = {
    "enabled": True,
    "contexts": {
        "graphql": {
            "rules": [
                # Max 600 requests per minute per user/IP
                {"name": "standard", "limit": 600, "window_seconds": 60},
            ]
        }
    }
}
```

## Next Steps

Now that your API is secure, let's look at advanced enterprise features like Webhooks and Subscriptions in [Tutorial 6: Advanced Features](./06_advanced.md).
