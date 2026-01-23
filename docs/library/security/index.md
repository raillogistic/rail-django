# Security Module Reference

The Rail Django security system provides comprehensive protection for your GraphQL API through multiple layers of defense.

## Security Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       Security Layers                            │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Request Layer                            │  │
│  │  Rate Limiting → Authentication → CORS → CSRF            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Query Layer                              │  │
│  │  Depth Limiting → Complexity → Cost Analysis              │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Authorization Layer                      │  │
│  │  RBAC → Model Permissions → Operation Guards              │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Data Layer                               │  │
│  │  Field Permissions → Masking → Input Validation           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Audit Layer                              │  │
│  │  Event Logging → Security Reports → Alerting              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Module Index

| Module | Path | Description |
|--------|------|-------------|
| [RBAC](./rbac.md) | `rail_django.security.rbac` | Role-Based Access Control |
| [Field Permissions](./field-permissions.md) | `rail_django.security.field_permissions` | Field-level access |
| [Input Validation](./validation.md) | `rail_django.security.validation` | Input sanitization |
| [Audit](./audit.md) | `rail_django.security.audit` | Security event logging |
| [Policies](./policies.md) | `rail_django.security.policies` | Allow/deny rules |
| [GraphQL Security](./graphql-security.md) | `rail_django.security.graphql` | Query protection |

## Quick Reference

### Enable/Disable Security Features

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        # Authentication
        "enable_authentication": True,

        # Authorization
        "enable_authorization": True,
        "enable_policy_engine": True,

        # Field-level
        "enable_field_permissions": True,
        "enable_object_permissions": True,

        # Input protection
        "enable_input_validation": True,
        "enable_sql_injection_protection": True,
        "enable_xss_protection": True,

        # Rate limiting
        "enable_rate_limiting": False,
        "rate_limit_requests_per_minute": 60,

        # Query protection
        "enable_query_depth_limiting": True,
    }
}
```

### Common Security Decorators

```python
from rail_django.security import (
    require_authentication,
    require_role,
    require_permission,
    validate_input
)

@require_authentication
def resolve_sensitive_data(root, info):
    """Requires authenticated user."""
    pass

@require_role("admin")
def resolve_admin_data(root, info):
    """Requires admin role."""
    pass

@require_permission("app.view_sensitive")
def resolve_restricted(root, info):
    """Requires specific permission."""
    pass

@validate_input
def mutate(cls, root, info, input):
    """Input is automatically sanitized."""
    pass
```

### Security Managers

```python
from rail_django.core.security import (
    get_auth_manager,
    get_authz_manager,
    get_input_validator
)

# Authentication manager
auth_manager = get_auth_manager("default")

# Authorization manager
authz_manager = get_authz_manager("default")

# Input validator
validator = get_input_validator("default")
```

## Security Settings Reference

### Authentication Settings

```python
"security_settings": {
    "enable_authentication": True,
    "session_timeout_minutes": 30,
}
```

### Authorization Settings

```python
"security_settings": {
    "enable_authorization": True,
    "enable_policy_engine": True,
    "enable_permission_cache": True,
    "permission_cache_ttl_seconds": 300,
    "enable_permission_audit": False,
}
```

### Input Validation Settings

```python
"security_settings": {
    "enable_input_validation": True,
    "enable_sql_injection_protection": True,
    "enable_xss_protection": True,
    "input_allow_html": False,
    "input_allowed_html_tags": ["p", "br", "strong", "em"],
    "input_max_string_length": None,  # None = no limit
    "input_truncate_long_strings": False,
    "input_failure_severity": "high",
}
```

### Rate Limiting Settings

```python
"security_settings": {
    "enable_rate_limiting": False,
    "rate_limit_requests_per_minute": 60,
    "rate_limit_requests_per_hour": 1000,
}
```

### File Upload Settings

```python
"security_settings": {
    "max_file_upload_size": 10 * 1024 * 1024,  # 10MB
    "allowed_file_types": [".jpg", ".jpeg", ".png", ".pdf", ".txt"],
}
```

### CORS Settings

```python
"security_settings": {
    "enable_cors": True,
    "allowed_origins": ["*"],  # Configure for production!
    "enable_csrf_protection": True,
}
```

### Query Protection Settings

```python
"performance_settings": {
    "max_query_depth": 10,
    "max_query_complexity": 1000,
    "enable_query_cost_analysis": False,
    "query_timeout": 30,
}
```

## Security Best Practices

### Production Checklist

1. **Authentication Required**
   ```python
   "schema_settings": {"authentication_required": True}
   ```

2. **Disable Introspection**
   ```python
   "schema_settings": {"enable_introspection": False}
   ```

3. **Enable Rate Limiting**
   ```python
   "security_settings": {"enable_rate_limiting": True}
   ```

4. **Configure CORS Properly**
   ```python
   "security_settings": {"allowed_origins": ["https://myapp.com"]}
   ```

5. **Enable Audit Logging**
   ```python
   "security_settings": {"enable_permission_audit": True}
   ```

6. **Limit Query Depth**
   ```python
   "performance_settings": {"max_query_depth": 5}
   ```

### Security Headers

Rail Django automatically sets security headers:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Content-Security-Policy: default-src 'self'
```

### Sensitive Data Handling

```python
class Customer(models.Model):
    email = models.EmailField()
    ssn = models.CharField(max_length=11)

    class GraphQLMeta:
        # Classify sensitive fields
        classifications = GraphQLMetaConfig.Classification(
            fields={
                "ssn": ["pii", "highly_sensitive"],
                "email": ["pii", "contact"]
            }
        )

        # Define access rules
        access = GraphQLMetaConfig.Access(
            fields=[
                GraphQLMetaConfig.FieldAccess(
                    field="ssn",
                    visibility="hidden",
                    roles=["compliance_officer"]
                ),
                GraphQLMetaConfig.FieldAccess(
                    field="email",
                    visibility="masked",
                    mask_value="***@***.***",
                    roles=["support"]
                )
            ]
        )
```

## Integration with Django

### Django Permissions

Rail Django integrates with Django's permission system:

```python
# Required permissions for mutations
"mutation_settings": {
    "require_model_permissions": True,
    "model_permission_codenames": {
        "create": "add",      # Requires app.add_model
        "update": "change",   # Requires app.change_model
        "delete": "delete"    # Requires app.delete_model
    }
}

# Required permissions for queries
"query_settings": {
    "require_model_permissions": True,
    "model_permission_codename": "view"  # Requires app.view_model
}
```

### Django Groups

Use Django groups as roles:

```python
from django.contrib.auth.models import Group

# Create groups
admin_group = Group.objects.create(name="admin")
viewer_group = Group.objects.create(name="viewer")

# Assign to users
user.groups.add(admin_group)
```

### Custom User Model

Rail Django works with custom user models:

```python
# Get user from request
user = info.context.user

# Check authentication
if not user.is_authenticated:
    raise GraphQLError("Authentication required")

# Check roles (via groups)
if user.groups.filter(name="admin").exists():
    # User has admin role
    pass
```

## Related Documentation

- [RBAC System](./rbac.md) - Detailed role-based access control
- [Field Permissions](./field-permissions.md) - Field-level security
- [Input Validation](./validation.md) - Input sanitization details
- [Audit System](./audit.md) - Security event logging
- [Authentication](../extensions/auth.md) - JWT authentication
