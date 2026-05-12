# Security, Authentication, and Permissions Reference

Rail Django uses a hybrid authorization system combining Django permissions, Role-Based Access Control (RBAC), Attribute-Based Access Control (ABAC), and Field-Level Security.

## Authentication (JWT & MFA)
- Configured in `RAIL_DJANGO_GRAPHQL.security_settings` and standard `JWT_*` settings.
- Exposes `login`, `verifyMfaLogin`, `refreshToken`, `revokeSession`, `logout` mutations.
- The `me` or `viewer` query fetches authenticated user details and resolved permissions/roles.

## Role-Based Access Control (RBAC)
Roles bundle Django permissions. Register roles in code (`role_manager`) or in `meta.yaml` inside app directories.

```python
from rail_django.security.rbac import role_manager, RoleDefinition, require_role

# Register Role
role_manager.register_role(
    RoleDefinition(
        name="catalog_manager",
        description="Manage catalog",
        permissions=["store.add_product", "store.change_product"],
        parent_roles=["catalog_viewer"]
    )
)

# Protect custom resolvers
@require_role("catalog_manager")
def resolve_custom_field(root, info): ...
```

### Contextual Permissions
Use suffixes like `_own` or `_assigned` for contextual checks (e.g., `accounts.update_profile_own`). The system resolves ownership via custom resolvers, model methods (`is_owner`), or fields (`owner`, `created_by`).

## Attribute-Based Access Control (ABAC)
Define rules based on Subject, Resource, Environment, or Action attributes. Can be global via `abac_manager.register_policy` or model-scoped in `GraphQLMeta`.

```python
class Document(models.Model):
    department = models.CharField(max_length=100)

    class GraphQLMeta(RailGraphQLMeta):
        abac_policies = [{
            "name": "same_department_only",
            "effect": "allow",
            "subject_conditions": {
                "department": { "operator": "eq", "target": "resource.department" }
            }
        }]
```

### Hybrid Strategy
Configured via `security_settings.hybrid_strategy` (e.g., `rbac_then_abac`, `rbac_or_abac`, `rbac_and_abac`). Combines RBAC and ABAC decisions.

## `GraphQLMeta` Access Control
Define operational guards and field guards directly on the model.

```python
class Order(models.Model):
    class GraphQLMeta(RailGraphQLMeta):
        access = RailGraphQLMeta.AccessControl(
            operations={
                "update": RailGraphQLMeta.OperationGuard(
                    roles=["order_manager"],
                    condition="can_modify_order", # points to static method
                    match="all" # Both role AND condition must pass
                )
            },
            fields=[
                RailGraphQLMeta.FieldGuard(
                    field="card_token",
                    access="read",
                    visibility="hidden", # or "masked"
                    roles=["admin"]
                )
            ]
        )
```

## Input Validation & Sanitization
Rail Django applies a unified validation pipeline (sanitizes strings, HTML allowlists, pattern detection).
- Configured in `security_settings` (e.g., `enable_input_validation`).
- Auto-applied to generated mutations.
- Use `@validate_input()` for custom resolvers.

## Policy Engine (Overrides)
Use `policy_manager` for cross-cutting allow/deny overrides with explicit priorities.

```python
policy_manager.register_policy(AccessPolicy(
    name="deny_contractors_tokens",
    effect=PolicyEffect.DENY,
    priority=100,
    roles=["contractor"],
    fields=["*token*"]
))
```

## Debugging Permissions
Use the `explainPermission` GraphQL query to debug why access was granted or denied. It details RBAC, ABAC, Hybrid, and Policy decisions.