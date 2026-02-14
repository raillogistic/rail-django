# Security module API

This reference maps the internal security modules to their runtime purpose in
`rail-django`.

## Security modules

- `rail_django.security.api`: Unified `security` event API.
- `rail_django.security.events`: Event types, builders, and event bus.
- `rail_django.security.rbac`: Role definitions and permission evaluation.
- `rail_django.security.policies`: Allow and deny policy engine.
- `rail_django.security.field_permissions`: Field visibility and masking rules.
- `rail_django.security.validation`: Input validation and sanitization.
- `rail_django.security.graphql`: Query analysis and security rules.

## Common settings used by security modules

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_authentication": True,
        "enable_authorization": True,
        "enable_policy_engine": True,
        "enable_field_permissions": True,
        "enable_input_validation": True,
        "enable_rate_limiting": False,
        "enable_permission_cache": True,
        "permission_cache_ttl_seconds": 300,
    },
    "performance_settings": {
        "max_query_depth": 10,
        "max_query_complexity": 1000,
    },
}
```

## Core APIs

Use RBAC and policy managers directly:

```python
from rail_django.security import role_manager, policy_manager
```

Use event emission API:

```python
from rail_django.security import security, EventType, Outcome

security.emit(
    EventType.AUTHZ_PERMISSION_DENIED,
    request=request,
    outcome=Outcome.DENIED,
    action="Permission denied",
)
```

Use input validation APIs:

```python
from rail_django.security.validation import validate_input, input_validator
```

## Runtime debugging via GraphQL

Permission inspection queries are exposed by the permissions extension:

- `myPermissions`
- `explainPermission`

These queries are useful for integration tests and permission troubleshooting.

## Next steps

- [RBAC internals](./rbac.md)
- [Permissions guide](../../security/permissions.md)
- [Validation guide](../../security/validation.md)
- [Security reference](../../reference/security.md)
