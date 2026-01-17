# Rail Django Permissions & Role Management Review

This document provides a comprehensive analysis of the current permissions and role management system in Rail Django, along with recommendations for improvement.

---

## Current Architecture Summary

The library implements a sophisticated multi-layered security system:

| Layer | Component | Purpose |
|-------|-----------|---------|
| RBAC | `RoleManager` | Role-based access with hierarchy |
| Policies | `PolicyManager` | Priority-based allow/deny engine |
| Field-Level | `FieldPermissionManager` | Access levels, visibility, masking |
| Declarative | `GraphQLMeta` | Per-model configuration |
| Config | `meta.json` | JSON-based role/permission definitions |
| Runtime | `FieldPermissionMiddleware` | Enforcement via middleware |

### Strengths

- Multi-layered defense
- Declarative configuration via `GraphQLMeta` and `meta.json`
- Field-level masking/redaction
- Contextual permissions (`_own`, `_assigned` suffixes)
- Role hierarchy support

### Key Files

| File | Purpose |
|------|---------|
| `rail_django/security/rbac.py` | RoleManager, RoleDefinition, decorators |
| `rail_django/security/policies.py` | AccessPolicy, PolicyManager |
| `rail_django/security/field_permissions.py` | FieldPermissionManager, field rules |
| `rail_django/security/graphql_security.py` | Query analysis, introspection protection |
| `rail_django/core/meta.py` | GraphQLMeta configuration classes |
| `rail_django/core/meta_json.py` | JSON-based meta.json loader |
| `rail_django/core/middleware.py` | FieldPermissionMiddleware |
| `rail_django/extensions/permissions.py` | PermissionQuery, PermissionManager |
| `rail_django/extensions/auth.py` | JWT auth with permission snapshots |
| `<app>/meta.json` | Declarative role/model configuration |

---

## Identified Issues and Recommendations

### 1. Undefined Scope Implementation

**Current Issue:** `PermissionScope` enum (GLOBAL, ORGANIZATION, DEPARTMENT, PROJECT, OBJECT) is defined in `rail_django/security/rbac.py:46-52` but never used in permission checks.

**Recommendation: Implement Hierarchical Scope Resolution**

```python
# Proposed: rail_django/security/scopes.py

@dataclass
class ScopeContext:
    """Runtime scope context for permission evaluation."""
    organization_id: Optional[int] = None
    department_id: Optional[int] = None
    project_id: Optional[int] = None
    object_id: Optional[int] = None

class ScopeResolver:
    """Resolves user's scope membership for hierarchical access."""

    def __init__(self):
        self._scope_resolvers: dict[PermissionScope, Callable] = {}

    def register_scope_resolver(self, scope: PermissionScope, resolver: Callable):
        """Register custom logic to determine user membership in a scope."""
        self._scope_resolvers[scope] = resolver

    def user_has_scope_access(
        self,
        user: User,
        required_scope: PermissionScope,
        context: ScopeContext
    ) -> bool:
        """Check if user has access at the required scope level."""
        # Cascade: GLOBAL > ORGANIZATION > DEPARTMENT > PROJECT > OBJECT
        ...
```

**Benefit:** Enables multi-tenant and organizational permission boundaries without code changes.

---

### 2. Adopt ABAC (Attribute-Based Access Control)

**Current Issue:** The system is primarily RBAC with some policy conditions via `Callable`. The conditions are ad-hoc and scattered.

**Recommendation: Implement Formal ABAC Engine**

```python
# Proposed: rail_django/security/abac.py

@dataclass
class AttributeContext:
    """Standardized attribute context for ABAC evaluation."""
    subject: dict   # User attributes: roles, department, clearance_level
    resource: dict  # Object attributes: owner_id, classification, status
    action: str     # Operation: read, write, delete
    environment: dict  # Time, IP, device, etc.

class ABACPolicy:
    """Declarative ABAC policy with standardized attributes."""

    def __init__(
        self,
        name: str,
        effect: PolicyEffect,
        subject_conditions: dict,   # {"clearance_level": {"gte": 3}}
        resource_conditions: dict,  # {"classification": {"in": ["public", "internal"]}}
        action_conditions: list,    # ["read", "list"]
        environment_conditions: dict = None,  # {"time": {"between": ["09:00", "17:00"]}}
    ):
        ...

class ABACEngine:
    """Evaluates ABAC policies with attribute extraction."""

    def __init__(self):
        self._attribute_extractors: dict[str, Callable] = {}
        self._policies: list[ABACPolicy] = []

    def register_attribute_extractor(self, attribute_name: str, extractor: Callable):
        """Register custom attribute extraction logic."""
        # e.g., extract user's clearance_level from profile
        ...

    def evaluate(self, context: AttributeContext) -> PolicyDecision:
        """Evaluate all applicable policies and return decision."""
        ...
```

**Usage in GraphQLMeta:**

```python
class SensitiveDocument(models.Model):
    classification = models.CharField(choices=["public", "internal", "confidential", "secret"])

    class GraphQLMeta:
        abac_policies = [
            ABACPolicy(
                name="classification_clearance_check",
                effect=PolicyEffect.ALLOW,
                subject_conditions={"clearance_level": {"gte": "$resource.classification_level"}},
                resource_conditions={},
                action_conditions=["read"],
            ),
        ]
```

**Benefit:** More expressive than role-based rules, handles complex access requirements like "users can only access documents at or below their clearance level."

---

### 3. Centralized Permission Registry

**Current Issue:** Permissions are scattered across:
- `RoleDefinition.permissions` (strings like `"store.view_order"`)
- Django's built-in `Permission` model
- `GraphQLMeta.operations` guards
- JSON `meta.json` files

**Recommendation: Single Permission Catalog**

```python
# Proposed: rail_django/security/permissions.py

@dataclass
class PermissionDefinition:
    """Canonical permission definition."""
    code: str                      # "store.order.read"
    name: str                      # "Read Orders"
    description: str
    category: str                  # "store", "admin", "system"
    scope_applicable: list[PermissionScope]  # Where this permission applies
    implied_by: list[str] = None   # Parent permissions that imply this
    implies: list[str] = None      # Child permissions this implies

class PermissionCatalog:
    """Central registry of all permissions in the system."""

    _permissions: dict[str, PermissionDefinition] = {}

    @classmethod
    def register(cls, permission: PermissionDefinition):
        cls._permissions[permission.code] = permission

    @classmethod
    def auto_discover(cls):
        """Scan models and generate CRUD permissions automatically."""
        for model in apps.get_models():
            app_label = model._meta.app_label
            model_name = model._meta.model_name
            for action in ["create", "read", "update", "delete", "list"]:
                cls.register(PermissionDefinition(
                    code=f"{app_label}.{model_name}.{action}",
                    name=f"{action.title()} {model._meta.verbose_name}",
                    description=f"Allows {action} on {model._meta.verbose_name}",
                    category=app_label,
                    scope_applicable=[PermissionScope.GLOBAL, PermissionScope.OBJECT],
                ))

    @classmethod
    def get_with_implied(cls, code: str) -> set[str]:
        """Get permission and all permissions it implies (transitive)."""
        ...
```

**Benefit:**
- Single source of truth for all permissions
- Permission implication chains (admin implies view)
- Auto-discovery reduces boilerplate

---

### 4. Policy-as-Code with DSL

**Current Issue:** Policies use Python `Callable` for conditions, which:
- Can't be serialized/stored in DB
- Hard to audit/review
- Can't be managed at runtime

**Recommendation: Implement a Policy DSL (Domain Specific Language)**

```python
# Proposed: rail_django/security/policy_dsl.py

class PolicyExpression:
    """Evaluable policy expression with safe parsing."""

    GRAMMAR = """
    expression  = comparison | boolean_expr
    boolean_expr = expression ("and" | "or") expression
    comparison  = attribute operator value
    attribute   = subject_attr | resource_attr | env_attr
    subject_attr = "subject." identifier
    resource_attr = "resource." identifier
    operator    = "==" | "!=" | ">" | "<" | ">=" | "<=" | "in" | "contains"
    """

    def __init__(self, expression: str):
        self.expression = expression
        self._ast = self._parse(expression)

    def evaluate(self, context: AttributeContext) -> bool:
        """Safely evaluate expression against context."""
        ...
```

**Usage in meta.json:**

```json
{
    "policies": [
        {
            "name": "owner_full_access",
            "effect": "allow",
            "condition": "subject.id == resource.owner_id",
            "actions": ["read", "update", "delete"]
        },
        {
            "name": "business_hours_only",
            "effect": "allow",
            "condition": "env.hour >= 9 and env.hour < 17 and env.weekday in [1,2,3,4,5]",
            "actions": ["*"]
        }
    ]
}
```

**Benefit:**
- Policies can be stored in database
- Runtime policy updates without deployment
- Auditable and reviewable
- Safe execution (no arbitrary code)

---

### 5. Separation of Permission Definition from Enforcement

**Current Issue:** `GraphQLMeta` mixes permission definition with schema configuration.

**Recommendation: Split into Separate Layers**

```
┌─────────────────────────────────────────────────────────────┐
│  DEFINITION LAYER                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Permission   │  │ Role         │  │ Policy           │   │
│  │ Catalog      │  │ Registry     │  │ Repository       │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  RESOLUTION LAYER                                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ AccessDecisionManager                                 │   │
│  │ - Combines RBAC + ABAC + Policies                     │   │
│  │ - Returns: ALLOW | DENY | NOT_APPLICABLE              │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  ENFORCEMENT LAYER                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │ Middleware  │  │ Decorators   │  │ Query Filtering   │   │
│  └─────────────┘  └──────────────┘  └───────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

```python
# Proposed: rail_django/security/access_decision.py

class AccessDecisionManager:
    """Unified access decision point combining all security layers."""

    def __init__(
        self,
        permission_catalog: PermissionCatalog,
        role_manager: RoleManager,
        policy_manager: PolicyManager,
        abac_engine: ABACEngine,
        scope_resolver: ScopeResolver,
    ):
        self._catalog = permission_catalog
        self._roles = role_manager
        self._policies = policy_manager
        self._abac = abac_engine
        self._scopes = scope_resolver

    def decide(
        self,
        user: User,
        permission: str,
        resource: Optional[Model] = None,
        operation: str = None,
        context: dict = None,
    ) -> AccessDecision:
        """
        Central decision point. Evaluation order:
        1. Explicit DENY policies (highest priority)
        2. ABAC policies
        3. Scope-based RBAC
        4. Standard RBAC
        5. Default deny
        """
        decision = AccessDecision(allowed=False, reason="default deny")

        # 1. Check explicit deny policies
        policy_decision = self._policies.evaluate(...)
        if policy_decision.effect == PolicyEffect.DENY:
            return AccessDecision(allowed=False, reason=policy_decision.reason)

        # 2. Check ABAC
        if self._abac.has_applicable_policy(...):
            abac_decision = self._abac.evaluate(...)
            if abac_decision.is_applicable:
                return abac_decision

        # 3. Check scope-based permissions
        scope_context = self._extract_scope_context(resource)
        if self._scopes.user_has_scope_access(user, ...):
            # Check permission within scope
            ...

        # 4. Standard RBAC
        if self._roles.has_permission(user, permission, context):
            return AccessDecision(allowed=True, reason="rbac")

        return decision
```

**Benefit:**
- Clear separation of concerns
- Single point for all access decisions
- Easier to test, audit, and extend

---

### 6. Runtime Permission Administration

**Current Issue:** Roles and permissions are defined in code/JSON, requiring deployment to change.

**Recommendation: Database-Backed Permission Management**

```python
# Proposed: rail_django/security/models.py

class DynamicRole(models.Model):
    """Database-stored role for runtime management."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    role_type = models.CharField(max_length=20, choices=RoleType.choices)
    permissions = models.ManyToManyField("DynamicPermission", related_name="roles")
    parent_roles = models.ManyToManyField("self", symmetrical=False, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class DynamicPermission(models.Model):
    """Database-stored permission."""
    code = models.CharField(max_length=200, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

class DynamicPolicy(models.Model):
    """Database-stored policy for runtime updates."""
    name = models.CharField(max_length=100)
    effect = models.CharField(choices=[("allow", "Allow"), ("deny", "Deny")])
    priority = models.IntegerField(default=0)
    condition_expression = models.TextField()  # DSL expression
    roles = models.JSONField(default=list)
    permissions = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)

class RoleAssignment(models.Model):
    """Track role assignments with scope and temporal validity."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(DynamicRole, on_delete=models.CASCADE)
    scope_type = models.CharField(max_length=20, choices=PermissionScope.choices)
    scope_id = models.PositiveIntegerField(null=True)  # Organization/Project/etc ID
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
```

**GraphQL Admin Mutations:**

```graphql
mutation {
  createRole(input: {
    name: "project_lead"
    roleType: BUSINESS
    permissions: ["project.manage", "team.view"]
  }) {
    role { id name }
  }

  assignRole(input: {
    userId: "123"
    roleId: "456"
    scopeType: PROJECT
    scopeId: "789"
    validUntil: "2026-06-01"
  }) {
    success
  }
}
```

**Benefit:**
- No deployment for permission changes
- Temporal role assignments (valid from/until)
- Scoped assignments (role in specific project/org)
- Full audit trail

---

### 7. Permission Caching Strategy

**Current Issue:** `RoleManager._permission_cache` uses simple dict with TTL, but doesn't handle cache invalidation on role/permission changes.

**Recommendation: Implement Proper Cache Invalidation**

```python
# Proposed: rail_django/security/caching.py

class PermissionCache:
    """Sophisticated permission caching with invalidation."""

    def __init__(self, cache_backend: str = "default", ttl: int = 300):
        self._cache = caches[cache_backend]
        self._ttl = ttl
        self._version_key = "permission_cache_version"

    def get_user_permissions(self, user_id: int) -> Optional[set[str]]:
        version = self._cache.get(self._version_key, 1)
        key = f"user_perms:{user_id}:v{version}"
        return self._cache.get(key)

    def set_user_permissions(self, user_id: int, permissions: set[str]):
        version = self._cache.get(self._version_key, 1)
        key = f"user_perms:{user_id}:v{version}"
        self._cache.set(key, permissions, self._ttl)

    def invalidate_user(self, user_id: int):
        """Invalidate specific user's cache."""
        # Delete user-specific keys
        ...

    def invalidate_role(self, role_name: str):
        """Invalidate cache for all users with this role."""
        # Could use cache tags or bump version
        ...

    def invalidate_all(self):
        """Invalidate all permission caches (nuclear option)."""
        self._cache.incr(self._version_key)

# Signals for automatic invalidation
@receiver(post_save, sender=RoleAssignment)
def invalidate_on_role_change(sender, instance, **kwargs):
    permission_cache.invalidate_user(instance.user_id)

@receiver(m2m_changed, sender=DynamicRole.permissions.through)
def invalidate_on_permission_change(sender, instance, **kwargs):
    permission_cache.invalidate_role(instance.name)
```

---

### 8. Simplified GraphQLMeta API

**Current Issue:** Verbose configuration with deeply nested structures.

**Recommendation: Cleaner Declarative Syntax**

```python
# Current (verbose):
class Order(models.Model):
    class GraphQLMeta:
        access = GraphQLMeta.AccessControl(
            operations={
                "list": GraphQLMeta.OperationGuard(
                    roles=["order_viewer"],
                    permissions=["store.view_order"],
                    require_authentication=True,
                ),
            },
        )

# Proposed (cleaner):
class Order(models.Model):
    class GraphQLMeta:
        # Simple role-based access
        read_roles = ["order_viewer", "order_manager", "admin"]
        write_roles = ["order_manager", "admin"]
        delete_roles = ["admin"]

        # Or permission-based
        read_permissions = ["store.view_order"]
        write_permissions = ["store.change_order"]

        # Field-level (simple)
        masked_fields = ["payment_token", "internal_notes"]
        hidden_fields = ["api_key"]

        # Advanced (when needed)
        access_policies = [
            Policy("owner_access", allow_if="subject.id == resource.owner_id"),
            Policy("business_hours", allow_if="env.hour.between(9, 17)"),
        ]
```

---

## Recommended Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                        CONFIGURATION LAYER                         │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐ │
│  │ GraphQL    │   │ meta.json  │   │ Database   │   │ Django     │ │
│  │ Meta       │   │ Files      │   │ Models     │   │ Admin      │ │
│  └─────┬──────┘   └─────┬──────┘   └─────┬──────┘   └─────┬──────┘ │
│        └────────────────┴────────────────┴────────────────┘        │
│                                    │                               │
├────────────────────────────────────┼───────────────────────────────┤
│                         REGISTRY LAYER                             │
│  ┌─────────────────────────────────┴─────────────────────────────┐ │
│  │                   UnifiedSecurityRegistry                     │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌────────────────────────┐ │ │
│  │  │ Permission  │  │ Role        │  │ Policy Repository      │ │ │
│  │  │ Catalog     │  │ Registry    │  │ (RBAC + ABAC + Custom) │ │ │
│  │  └─────────────┘  └─────────────┘  └────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────────────────────┤
│                         DECISION LAYER                             │
│  ┌────────────────────────────────────────────────────────────────┐│
│  │                    AccessDecisionManager                       ││
│  │  1. Deny policies → 2. ABAC → 3. Scoped RBAC → 4. Default deny ││
│  └────────────────────────────────────────────────────────────────┘│
├────────────────────────────────────────────────────────────────────┤
│                        ENFORCEMENT LAYER                           │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐ │
│  │ Middleware │   │ Decorators │   │ Query      │   │ Field      │ │
│  │            │   │            │   │ Filtering  │   │ Masking    │ │
│  └────────────┘   └────────────┘   └────────────┘   └────────────┘ │
├────────────────────────────────────────────────────────────────────┤
│                          AUDIT LAYER                               │
│  ┌────────────────────────────────────────────────────────────────┐│
│  │ Permission audit trail + Decision logging + Change tracking    ││
│  └────────────────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────────────┘
```

---

## Summary of Recommendations

| Priority | Recommendation | Effort | Impact |
|----------|----------------|--------|--------|
| **High** | Implement `AccessDecisionManager` (single decision point) | Medium | High - cleaner architecture |
| **High** | Database-backed dynamic roles/permissions | Medium | High - runtime management |
| **High** | Implement scope resolution for multi-tenancy | Medium | High - enables org boundaries |
| **Medium** | ABAC engine with attribute extractors | Medium | Medium - complex scenarios |
| **Medium** | Policy DSL for safe, auditable conditions | Medium | Medium - runtime policies |
| **Medium** | Proper cache invalidation | Low | Medium - performance + correctness |
| **Low** | Simplified GraphQLMeta API | Low | Low - DX improvement |
| **Low** | Permission catalog with auto-discovery | Low | Low - reduces boilerplate |

---

## Current Permission Check Flow

```
1. Request arrives with JWT token
   │
2. AuthenticationMiddleware extracts user
   │
3. AccessGuardMiddleware checks schema-level auth requirements
   │
4. For each field resolved:
   │
   ├──► FieldPermissionMiddleware
   │    │
   │    ├──► Policy Engine (policies.py)
   │    │    - Checks registered AccessPolicies
   │    │    - Returns decision if policy matches
   │    │
   │    ├──► RBAC Check (rbac.py)
   │    │    - Superuser? Allow all
   │    │    - Get effective permissions from roles
   │    │    - Check contextual permissions (_own, _assigned)
   │    │
   │    ├──► Field Permission Rules (field_permissions.py)
   │    │    - Check field-specific rules
   │    │    - Apply visibility/masking
   │    │
   │    └──► Django Permissions (fallback)
   │         - Check app_label.view_model permissions
```

---

## Next Steps

1. **Phase 1:** Implement `AccessDecisionManager` as the single decision point
2. **Phase 2:** Add database models for dynamic role/permission management
3. **Phase 3:** Implement scope resolution for multi-tenant scenarios
4. **Phase 4:** Add ABAC engine for complex attribute-based rules
5. **Phase 5:** Implement Policy DSL for runtime-manageable policies
