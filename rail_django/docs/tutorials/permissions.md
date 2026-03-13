# Permissions tutorial

This tutorial shows you how to secure a Rail Django API with role-based
access control, attribute-based access control, field-level restrictions, and
hybrid policies.

You will learn the parts that Rail Django already gives you by default, the
parts you must define yourself, and how to combine them without creating a
permission model that becomes impossible to reason about later.

Every example on this page is based on APIs that exist in the current
codebase.

That includes:

- `role_manager`, `RoleDefinition`, and `PermissionContext`
- `require_role` and `require_permission`
- `ABACPolicy`, `MatchCondition`, `ConditionOperator`, and `abac_manager`
- `require_attributes`
- `policy_manager` and `AccessPolicy`
- `GraphQLMeta.AccessControl`, `GraphQLMeta.OperationGuard`,
  `GraphQLMeta.FieldGuard`, and `GraphQLMeta.Classification`
- the GraphQL inspection queries `myPermissions` and `explainPermission`

By the end of the tutorial, you will know when to use RBAC, when to use ABAC,
and when to combine both.

## What Rail Django does before you add custom rules

Rail Django already applies a strong baseline before you start writing custom
authorization code.

For generated GraphQL operations:

- list and retrieve queries can require Django model permissions
- create, update, and delete mutations can require Django model permissions
- field permissions can hide or mask sensitive fields
- the policy engine can override field and permission outcomes
- the hybrid engine can combine RBAC and ABAC in one decision

The defaults in `rail_django.config.defaults` matter here.

At the time of writing, the library defaults include:

- `query_settings.require_model_permissions = True`
- `query_settings.model_permission_codename = "view"`
- `mutation_settings.require_model_permissions = True`
- `mutation_settings.model_permission_codenames = {"create": "add",
  "update": "change", "delete": "delete"}`
- `security_settings.enable_authorization = True`
- `security_settings.enable_policy_engine = True`
- `security_settings.enable_field_permissions = True`
- `security_settings.enable_abac = True`
- `security_settings.hybrid_strategy = "rbac_then_abac"`

That means you usually start from a deny-by-default posture for generated
operations, then add business rules on top.

## RBAC, ABAC, and policy overrides

You will get better results if you choose the right tool for the right kind of
decision.

Use RBAC when the question is mostly:

- what job does this person have
- what action is this role allowed to perform
- which Django model permissions belong to that role

Use ABAC when the question is mostly:

- does this record belong to the same department as the user
- is this request coming during business hours
- is the user on the corporate network
- is the record high risk, regulated, or tenant scoped

Use the policy engine when you need a cross-cutting override such as:

- deny every contractor from seeing token fields
- mask all financial fields unless the role is finance or admin
- allow a narrow exception with higher priority than your baseline rules

Use the hybrid engine when both statements are true:

1. A user must belong to the correct role or hold the correct permission.
2. The runtime context must also pass a resource or environment check.

## How the decision flow works

Rail Django does not evaluate everything in a random order.

The actual flow is:

1. The policy engine runs first when it is enabled.
2. RBAC checks run through `role_manager`.
3. ABAC checks run when `security_settings.enable_abac` is enabled.
4. The hybrid strategy combines RBAC and ABAC.
5. Field rules and field policies decide whether a value is visible, hidden,
   or masked.

This order matters.

For example:

- a high-priority deny policy can block an action before RBAC or ABAC grants it
- a user can have the right role and still fail ABAC
- a user can read a model and still see a field as masked

## Permission naming conventions

Rail Django works best when you use a predictable permission naming strategy.

Use Django model permissions for CRUD work:

- `store.view_product`
- `store.add_product`
- `store.change_product`
- `store.delete_product`

Use custom permissions for business actions:

- `billing.approve_refund`
- `security.rotate_api_key`
- `history.read`

Use contextual suffixes when the permission depends on the specific object:

- `profile.update_own`
- `ticket.update_assigned`

The current RBAC implementation treats `_own` and `_assigned` specially.

For those permissions to succeed, two things must be true:

1. The user must hold the permission through a role or Django permissions.
2. The runtime `PermissionContext` must confirm ownership or assignment.

If either condition fails, access is denied.

## Configure the project first

Start with a clean, explicit security configuration in `settings.py`.

This example keeps the generated API strict and predictable:

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "authentication_required": True,
        "auto_camelcase": True,
    },
    "query_settings": {
        "require_model_permissions": True,
        "model_permission_codename": "view",
    },
    "mutation_settings": {
        "require_model_permissions": True,
        "model_permission_codenames": {
            "create": "add",
            "update": "change",
            "delete": "delete",
        },
    },
    "security_settings": {
        "enable_authorization": True,
        "enable_policy_engine": True,
        "enable_permission_cache": True,
        "permission_cache_ttl_seconds": 300,
        "enable_permission_audit": True,
        "permission_audit_log_all": False,
        "permission_audit_log_denies": True,
        "enable_field_permissions": True,
        "field_permission_input_mode": "reject",
        "enable_abac": True,
        "hybrid_strategy": "rbac_then_abac",
        "abac_audit_decisions": False,
    },
    "middleware_settings": {
        "enable_field_permission_middleware": True,
    },
}
```

This baseline gives you:

- authenticated GraphQL access
- model-level permission checks for generated CRUD operations
- field-level masking and hiding
- audit events for denied permission checks
- hybrid RBAC plus ABAC evaluation

## Generated CRUD versus hand-written resolvers

Rail Django has two different permission entry points, and it helps to keep
them separate in your head.

Generated list, retrieve, create, update, and delete operations mostly rely
on:

- Django model permissions such as `app.view_model` and `app.change_model`
- `GraphQLMeta.OperationGuard`
- the mutation pipeline, which can run hybrid ABAC checks when enabled

Hand-written resolvers usually rely on:

- `@require_role`
- `@require_permission`
- `@require_attributes`
- direct service-layer checks with `role_manager.has_permission()`

That means you should not assume the generated API is calling your resolver
decorators behind the scenes.

Use `GraphQLMeta` for generated operations.

Use decorators or service functions for custom resolvers.

## The main RBAC APIs

You will use a small set of RBAC APIs most of the time.

Register roles in code:

```python
from rail_django.security import RoleDefinition, RoleType, role_manager

role_manager.register_role(
    RoleDefinition(
        name="catalog_manager",
        description="Manage catalog items.",
        role_type=RoleType.BUSINESS,
        permissions=[
            "store.view_product",
            "store.add_product",
            "store.change_product",
            "store.delete_product",
        ],
    )
)
```

Assign roles through Django groups:

```python
user = User.objects.get(username="ada")
role_manager.assign_role_to_user(user, "catalog_manager")
```

Check permissions directly:

```python
allowed = role_manager.has_permission(user, "store.change_product")
```

Explain a permission decision:

```python
explanation = role_manager.explain_permission(
    user,
    "store.change_product",
)
```

Protect a resolver with decorators:

```python
from rail_django.security import require_permission, require_role

@require_role("catalog_manager")
def resolve_catalog_admin_view(root, info):
    ...


@require_permission("store.change_product")
def resolve_product_editor(root, info):
    ...
```

## The main ABAC APIs

You will use ABAC when a plain role name is not enough.

Register a policy:

```python
from rail_django.security import (
    ABACPolicy,
    ConditionOperator,
    MatchCondition,
    abac_manager,
)

abac_manager.register_policy(
    ABACPolicy(
        name="department_isolation",
        effect="allow",
        priority=50,
        subject_conditions={
            "department": MatchCondition(
                ConditionOperator.EQ,
                target="resource.department",
            )
        },
    )
)
```

Protect a resolver with inline ABAC:

```python
from rail_django.security import require_attributes

@require_attributes(
    subject_conditions={
        "is_staff": {"operator": "eq", "value": True}
    }
)
def resolve_internal_dashboard(root, info):
    ...
```

Attach model-scoped ABAC policies through `GraphQLMeta`:

```python
from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta


class Document(models.Model):
    department = models.CharField(max_length=100)

    class GraphQLMeta(RailGraphQLMeta):
        abac_policies = [
            {
                "name": "same_department_only",
                "effect": "allow",
                "priority": 50,
                "subject_conditions": {
                    "department": {
                        "operator": "eq",
                        "target": "resource.department",
                    }
                },
            }
        ]
```

Rail Django namespaces `GraphQLMeta` ABAC policies per model when it registers
them.

## The ABAC attributes you get out of the box

You do not have to build every ABAC attribute yourself.

The built-in providers already expose useful data.

Subject attributes include:

- `authenticated`
- `user_id`
- `username`
- `email`
- `is_staff`
- `is_superuser`
- `is_active`
- `roles`
- profile attributes such as `department`, `organization`, `team`,
  `location`, and `level` when `user.profile` exists

Resource attributes include:

- `model_name`
- `app_label`
- `model_label`
- every concrete field value on the model instance
- `owner_id` when the model has `owner_id`, `created_by_id`, or `user_id`
- `classification` and `sensitivity` when defined on `GraphQLMeta`

Environment attributes include:

- `current_time`
- `current_date`
- `day_of_week`
- `hour`
- `is_business_hours`
- `client_ip`
- `user_agent`
- `is_secure`
- `request_method`
- `request_path`

Action attributes include:

- `type`
- `permission`
- `operation_name`

## Contextual permission rules

Contextual RBAC is useful when you want a short permission string that still
checks the current object.

Rail Django currently recognizes these contextual suffixes:

- `_own`
- `_assigned`

Ownership is resolved in this order:

1. A custom resolver registered with `register_owner_resolver`
2. A model method named `is_owner`, `is_owned_by`, or `owned_by`
3. A direct attribute named `owner`, `created_by`, or `user`

Assignment is resolved in this order:

1. A custom resolver registered with `register_assignment_resolver`
2. A model method named `is_assigned` or `is_assigned_to`
3. A direct attribute named `assigned_to`
4. A many-to-many relation named `assignees`

That means you can keep your permission strings stable even when your real
data model is more complex.

## A shared sample domain

The next sections use a set of realistic business scenarios.

Imagine you are building one platform that serves:

- a retail catalog
- customer support
- human resources
- banking approvals
- healthcare operations
- school administration
- a multi-tenant SaaS product

The code snippets are independent examples.

You do not need to use every pattern in one project.

## Case 1: Retail catalog viewers can read products

This first case shows the simplest RBAC pattern.

A retail company wants store staff to browse products, but only managers can
change them.

Create a read-only role:

```python
from rail_django.security import RoleDefinition, RoleType, role_manager

role_manager.register_role(
    RoleDefinition(
        name="catalog_viewer",
        description="Read-only access to the product catalog.",
        role_type=RoleType.FUNCTIONAL,
        permissions=["store.view_product"],
    )
)
```

Assign the role:

```python
role_manager.assign_role_to_user(user, "catalog_viewer")
```

Protect a resolver:

```python
from rail_django.security import require_permission


@require_permission("store.view_product")
def resolve_products(root, info):
    return Product.objects.all()
```

Why this works:

- the role grants `store.view_product`
- the resolver only checks one permission
- the rule is easy to explain to auditors and product owners

Use this pattern when the business rule is literally "people in this role can
read this model."

## Case 2: Catalog managers inherit from catalog viewers

This case shows role inheritance.

A catalog manager should automatically keep every viewer permission without you
copying the same list everywhere.

Define the child role with `parent_roles`:

```python
role_manager.register_role(
    RoleDefinition(
        name="catalog_manager",
        description="Manage the retail catalog.",
        role_type=RoleType.BUSINESS,
        permissions=[
            "store.add_product",
            "store.change_product",
            "store.delete_product",
        ],
        parent_roles=["catalog_viewer"],
    )
)
```

Now the manager gets:

- every permission listed on `catalog_manager`
- every permission listed on `catalog_viewer`

Use this when your domain has clear seniority layers such as:

- viewer to editor to admin
- agent to supervisor to director
- analyst to approver to controller

This pattern reduces duplication and keeps permission reviews shorter.

## Case 3: Customers can update only their own profile

This case uses contextual RBAC with `_own`.

A consumer app lets users edit their own profile, but never another user's
profile.

Register a role that grants the contextual permission:

```python
role_manager.register_role(
    RoleDefinition(
        name="customer_self_service",
        description="Customers can manage their own profile.",
        role_type=RoleType.BUSINESS,
        permissions=["accounts.update_profile_own"],
    )
)
```

Build a context when you check the permission:

```python
from rail_django.security import PermissionContext, role_manager


def update_profile(user, profile, payload):
    context = PermissionContext(
        user=user,
        object_instance=profile,
        operation="update",
    )

    if not role_manager.has_permission(
        user,
        "accounts.update_profile_own",
        context,
    ):
        raise PermissionDenied("You can only edit your own profile.")

    for field, value in payload.items():
        setattr(profile, field, value)
    profile.save()
```

If `profile.user == user`, access succeeds.

If not, the decision fails with a `not_owner` style reason.

This is the right pattern when a customer owns exactly one record or a small
set of clearly owned records.

## Case 4: Support agents can update only assigned tickets

This case uses contextual RBAC with `_assigned`.

A support team wants any agent to read all tickets, but only the assigned agent
can update the ticket status.

Define the role:

```python
role_manager.register_role(
    RoleDefinition(
        name="support_agent",
        description="Work on assigned support tickets.",
        role_type=RoleType.BUSINESS,
        permissions=[
            "support.view_ticket",
            "support.update_ticket_assigned",
        ],
    )
)
```

Check the permission against a specific ticket:

```python
def update_ticket_status(user, ticket, new_status):
    context = PermissionContext(
        user=user,
        object_instance=ticket,
        operation="update",
    )

    if not role_manager.has_permission(
        user,
        "support.update_ticket_assigned",
        context,
    ):
        raise PermissionDenied("Only the assigned agent can update this ticket.")

    ticket.status = new_status
    ticket.save()
```

This works well when your model already has:

- `assigned_to`
- `assignees`
- or a custom assignment resolver

Use it in support desks, dispatch systems, editorial queues, and legal review
workflows.

## Case 5: Department isolation with model-level ABAC

This case moves from roles to attributes.

A hospital wants staff to access patient documents only when the user's
department matches the document's department.

Attach the policy to the model:

```python
from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta


class PatientDocument(models.Model):
    department = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    body = models.TextField()

    class GraphQLMeta(RailGraphQLMeta):
        abac_policies = [
            {
                "name": "same_department_only",
                "description": "Staff stay inside their department boundary.",
                "effect": "allow",
                "priority": 100,
                "subject_conditions": {
                    "department": {
                        "operator": "eq",
                        "target": "resource.department",
                    }
                },
            }
        ]
```

Why this is better than pure RBAC:

- you do not need one role per department
- HR and radiology can share the same base role but still stay isolated
- the rule follows the record, not the URL shape

This is one of the strongest ABAC use cases in Rail Django because the engine
already exposes both `subject.department` and `resource.department`.

## Case 6: Finance dashboards are available only during business hours

This case uses environment attributes.

A finance team can read revenue reports only between 08:00 and 18:00 UTC.

Register an ABAC policy:

```python
abac_manager.register_policy(
    ABACPolicy(
        name="finance_business_hours",
        effect="allow",
        priority=40,
        subject_conditions={
            "roles": MatchCondition(
                ConditionOperator.INTERSECTS,
                value=["finance_analyst", "finance_controller"],
            )
        },
        environment_conditions={
            "hour": MatchCondition(
                ConditionOperator.BETWEEN,
                value=[8, 18],
            )
        },
    )
)
```

This works because the environment provider exposes `hour`.

Use this pattern when your regulator or internal policy cares about:

- business hours only access
- weekday only changes
- after-hours restrictions for dangerous operations

If you need local timezone behavior, normalize the time before it reaches the
policy or place the timezone-aware value in a custom provider.

## Case 7: Internal tools are available only from the company network

This case uses the request environment.

A logistics company wants shipment control screens to work only from the
corporate VPN or office network.

Register a deny policy first:

```python
abac_manager.register_policy(
    ABACPolicy(
        name="deny_non_corporate_ip_for_ops",
        effect="deny",
        priority=100,
        action_conditions={
            "permission": MatchCondition(
                ConditionOperator.EQ,
                value="ops.change_shipment",
            )
        },
        environment_conditions={
            "client_ip": MatchCondition(
                ConditionOperator.NOT_IN,
                value=["10.0.0.8", "10.0.0.9", "10.0.0.10"],
            )
        },
    )
)
```

Then keep your normal RBAC rule:

```python
role_manager.register_role(
    RoleDefinition(
        name="shipment_controller",
        description="Manage shipment states.",
        role_type=RoleType.BUSINESS,
        permissions=["ops.change_shipment"],
    )
)
```

The role answers "who may do this."

The ABAC rule answers "from where may they do this."

That split is easy to explain and easy to test.

## Case 8: Contractors are blocked from secret fields everywhere

This case uses the policy engine as a cross-cutting override.

An enterprise SaaS platform lets contractors work in many modules, but they
must never see token or secret fields.

Register a deny policy:

```python
from rail_django.security import AccessPolicy, PolicyEffect, policy_manager

policy_manager.register_policy(
    AccessPolicy(
        name="deny_secret_fields_for_contractors",
        effect=PolicyEffect.DENY,
        priority=100,
        roles=["contractor"],
        fields=["*token*", "*secret*"],
        reason="Contractors cannot access secret-bearing fields.",
    )
)
```

Why use a policy here instead of field guards on every model:

- the rule applies across the whole platform
- it has an explicit priority
- it is easier to audit than repeating the same field guard on many models

Use policy rules for global exceptions and hard bans.

Do not use them as your only permission model, or you will create a policy
list that nobody can maintain.

## Case 9: Product browsing is public, but writes are private

This case uses `GraphQLMeta.OperationGuard`.

An online store wants anonymous visitors to list and retrieve products, while
catalog changes stay restricted to authenticated staff.

Declare the guards on the model:

```python
from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta


class Product(models.Model):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class GraphQLMeta(RailGraphQLMeta):
        access = RailGraphQLMeta.AccessControl(
            operations={
                "list": RailGraphQLMeta.OperationGuard(
                    roles=["catalog_viewer", "catalog_manager"],
                    permissions=["store.view_product"],
                    require_authentication=False,
                    allow_anonymous=True,
                ),
                "retrieve": RailGraphQLMeta.OperationGuard(
                    roles=["catalog_viewer", "catalog_manager"],
                    permissions=["store.view_product"],
                    require_authentication=False,
                    allow_anonymous=True,
                ),
                "create": RailGraphQLMeta.OperationGuard(
                    roles=["catalog_manager"],
                    permissions=["store.add_product"],
                ),
                "update": RailGraphQLMeta.OperationGuard(
                    roles=["catalog_manager"],
                    permissions=["store.change_product"],
                ),
                "delete": RailGraphQLMeta.OperationGuard(
                    roles=["catalog_manager"],
                    permissions=["store.delete_product"],
                ),
            }
        )
```

This is useful when your public and private rules are both model-centric.

It also keeps the access design close to the model instead of scattering
behavior across resolver files.

## Case 10: HR can view salary, but managers see a mask

This case uses field guards.

A company wants only HR and finance staff to see exact salary amounts.

Everyone else can see that a salary exists, but not the number.

Declare a field guard:

```python
class Employee(models.Model):
    salary = models.DecimalField(max_digits=10, decimal_places=2)
    department = models.CharField(max_length=100)

    class GraphQLMeta(RailGraphQLMeta):
        access = RailGraphQLMeta.AccessControl(
            fields=[
                RailGraphQLMeta.FieldGuard(
                    field="salary",
                    access="read",
                    visibility="visible",
                    roles=["hr_admin", "finance_controller"],
                ),
                RailGraphQLMeta.FieldGuard(
                    field="salary",
                    access="read",
                    visibility="masked",
                    mask_value="***CONFIDENTIAL***",
                    roles=["department_manager"],
                ),
            ]
        )
```

What happens in practice:

- HR sees the real salary
- finance sees the real salary
- department managers see a masked value
- other users may fall back to default masking or hiding rules

Field-level design matters because model-level access is rarely enough for
payroll, health data, customer secrets, or fraud signals.

## Case 11: Unauthorized writes are rejected at input time

This case extends field permissions to mutation inputs.

A billing system wants only finance staff to edit `credit_limit`, even if the
user can update other parts of the customer record.

Set the input mode:

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_field_permissions": True,
        "field_permission_input_mode": "reject",
    }
}
```

Declare the guarded field:

```python
class CustomerAccount(models.Model):
    name = models.CharField(max_length=200)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2)

    class GraphQLMeta(RailGraphQLMeta):
        access = RailGraphQLMeta.AccessControl(
            fields=[
                RailGraphQLMeta.FieldGuard(
                    field="credit_limit",
                    access="write",
                    visibility="visible",
                    roles=["finance_controller"],
                )
            ]
        )
```

If a sales user submits a mutation that changes `creditLimit`, the middleware
can reject the request before the data reaches your save logic.

That is the right choice when silent stripping would hide a dangerous client
bug.

Use `"strip"` instead only when your product team explicitly wants partial
success semantics.

## Case 12: Bank transfer approval requires both role and condition

This case uses `match="all"` inside an operation guard.

A bank lets only approvers review wire transfers, and the approver must also
be assigned to the branch that owns the transfer.

Declare the model and condition:

```python
class WireTransfer(models.Model):
    branch_manager = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="managed_transfers",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    @staticmethod
    def can_approve_transfer(
        user=None,
        instance=None,
        **kwargs,
    ):
        if user is None or instance is None:
            return False
        return instance.branch_manager_id == user.id

    class GraphQLMeta(RailGraphQLMeta):
        access = RailGraphQLMeta.AccessControl(
            operations={
                "update": RailGraphQLMeta.OperationGuard(
                    roles=["wire_approver"],
                    permissions=["bank.change_wiretransfer"],
                    condition="can_approve_transfer",
                    match="all",
                    deny_message=(
                        "Only the assigned branch approver can update this "
                        "wire transfer."
                    ),
                )
            }
        )
```

This is a strong pattern for approvals because it expresses:

- the user must be in the right job function
- the user must also match the specific record

Use `match="all"` for high-risk actions.

Use the default `match="any"` only when any one signal is enough.

## Case 13: Emergency access uses a hybrid override

This case shows a controlled break-glass flow.

A hospital wants ordinary chart access to follow strict RBAC, but an on-call
incident commander may access records during emergencies even without the usual
department role.

Set the hybrid strategy:

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_abac": True,
        "hybrid_strategy": "rbac_or_abac",
    }
}
```

Keep your normal RBAC:

```python
role_manager.register_role(
    RoleDefinition(
        name="clinical_staff",
        description="Standard clinical record access.",
        role_type=RoleType.BUSINESS,
        permissions=["health.view_chart"],
    )
)
```

Add the emergency ABAC rule:

```python
abac_manager.register_policy(
    ABACPolicy(
        name="incident_break_glass",
        effect="allow",
        priority=90,
        subject_conditions={
            "roles": MatchCondition(
                ConditionOperator.INTERSECTS,
                value=["incident_commander"],
            )
        },
        environment_conditions={
            "request_path": MatchCondition(
                ConditionOperator.STARTS_WITH,
                value="/graphql",
            )
        },
        action_conditions={
            "permission": MatchCondition(
                ConditionOperator.EQ,
                value="health.view_chart",
            )
        },
    )
)
```

In `rbac_or_abac` mode:

- ordinary staff can pass RBAC
- the incident commander can pass ABAC
- either signal is enough

This is powerful, so document it well and audit it aggressively.

## Case 14: Tenant admins stay inside their own organization

This case uses ABAC for tenant isolation.

A B2B SaaS platform gives every customer an organization admin role, but the
admin must never touch another customer's records.

Assume your model has an `organization` field and the user's profile also has
an `organization` attribute.

Register the policy:

```python
abac_manager.register_policy(
    ABACPolicy(
        name="tenant_boundary",
        effect="allow",
        priority=80,
        subject_conditions={
            "organization": MatchCondition(
                ConditionOperator.EQ,
                target="resource.organization",
            )
        },
    )
)
```

Keep the role small:

```python
role_manager.register_role(
    RoleDefinition(
        name="tenant_admin",
        description="Administer one tenant.",
        role_type=RoleType.BUSINESS,
        permissions=[
            "saas.view_subscription",
            "saas.change_subscription",
        ],
    )
)
```

This avoids the classic anti-pattern of creating:

- `tenant_1_admin`
- `tenant_2_admin`
- `tenant_3_admin`

ABAC is a much better fit for per-tenant boundaries.

## Case 15: Teachers can view only students assigned to their class

This case uses a custom assignment resolver.

In a school system, each teacher belongs to several classes through a join
table, so `assigned_to` does not exist directly on the student record.

Register the contextual role:

```python
role_manager.register_role(
    RoleDefinition(
        name="teacher",
        description="Teachers can view assigned students.",
        role_type=RoleType.BUSINESS,
        permissions=["school.view_student_assigned"],
    )
)
```

Register a custom assignment resolver:

```python
def student_assignment_resolver(context):
    student = context.object_instance
    teacher = context.user
    if student is None or teacher is None:
        return False
    return student.classes.filter(teachers=teacher).exists()


role_manager.register_assignment_resolver(
    "school.student",
    student_assignment_resolver,
)
```

Use it at runtime:

```python
context = PermissionContext(
    user=request.user,
    object_instance=student,
    operation="read",
)

allowed = role_manager.has_permission(
    request.user,
    "school.view_student_assigned",
    context,
)
```

This pattern is excellent when ownership or assignment is stored in a join
table, not a single foreign key.

## Case 16: Marketplace vendors can edit only their own products

This case uses a custom owner resolver.

A marketplace platform stores vendor ownership indirectly through a seller
account, so plain `product.owner == user` does not work.

Create the role:

```python
role_manager.register_role(
    RoleDefinition(
        name="vendor",
        description="Manage one vendor's products.",
        role_type=RoleType.BUSINESS,
        permissions=["market.change_product_own"],
    )
)
```

Register a custom owner resolver:

```python
def product_owner_resolver(context):
    product = context.object_instance
    user = context.user
    if product is None or user is None:
        return False
    return product.seller.account_manager_id == user.id


role_manager.register_owner_resolver(
    "market.product",
    product_owner_resolver,
)
```

Then evaluate the permission with context:

```python
context = PermissionContext(
    user=request.user,
    object_instance=product,
    operation="update",
)

if not role_manager.has_permission(
    request.user,
    "market.change_product_own",
    context,
):
    raise PermissionDenied("You can edit only your own catalog items.")
```

This lets you preserve a clean permission name even when the real ownership
path is long.

## Case 17: Fraud analysts see only high-risk claims

This case shows a custom ABAC provider.

A large insurer wants fraud analysts to see claims only when an external risk
engine says the score is at least 80.

Create a provider:

```python
from rail_django.security import AttributeSet, BaseAttributeProvider, abac_manager


class FraudSignalsProvider(BaseAttributeProvider):
    def collect(self, instance=None, **kwargs):
        score = None
        if instance is not None:
            score = getattr(instance, "fraud_score", None)
        return AttributeSet(
            static_attributes={
                "risk_score": score,
            }
        )


abac_manager.register_provider("fraud", FraudSignalsProvider())
```

Register the policy:

```python
abac_manager.register_policy(
    ABACPolicy(
        name="fraud_queue_threshold",
        effect="allow",
        priority=70,
        subject_conditions={
            "roles": MatchCondition(
                ConditionOperator.INTERSECTS,
                value=["fraud_analyst"],
            )
        },
        environment_conditions={
            "fraud.risk_score": MatchCondition(
                ConditionOperator.GTE,
                value=80,
            )
        },
    )
)
```

Custom providers are stored under environment keys with the provider name as a
prefix.

That is why the policy checks `fraud.risk_score`.

Use a custom provider when the rule depends on:

- feature flags
- risk engines
- contract entitlements
- regional compliance services

## Case 18: Resolver-level ABAC protects a sensitive export

This case uses `require_attributes`.

A compliance team can export transaction history only if the user is staff and
the request is secure.

Protect the resolver inline:

```python
from rail_django.security import require_attributes


@require_attributes(
    subject_conditions={
        "is_staff": {
            "operator": "eq",
            "value": True,
        }
    },
    environment_conditions={
        "is_secure": {
            "operator": "eq",
            "value": True,
        }
    },
    action_conditions={
        "type": {
            "operator": "in",
            "value": ["query", "mutation"],
        }
    },
    message="Only internal secure requests can export transactions.",
)
def resolve_export_transactions(root, info, start_date, end_date):
    return build_export(start_date, end_date)
```

This is useful when:

- the rule belongs to one resolver, not the whole model
- the model does not need a reusable global policy
- you want a local guard with a custom error message

Inline ABAC is especially helpful for exports, reports, and operations that do
not map cleanly to one CRUD permission.

## Case 19: Use GraphQL to explain why access was denied

This case focuses on debugging.

A support engineer says, "The user has the role, but the request is still
failing."

Ask the API, not your memory.

Use `myPermissions` to inspect the broad model matrix:

```graphql
query MyPermissions {
  myPermissions(modelName: "store.Product") {
    modelName
    canRead
    canCreate
    canUpdate
    canDelete
  }
}
```

Use `explainPermission` for the exact rule:

```graphql
query ExplainPermission {
  explainPermission(
    permission: "store.change_product"
    modelName: "store.Product"
    objectId: "42"
    operation: "update"
  ) {
    allowed
    reason
    roles
    effectivePermissions
    contextRequired
    contextAllowed
    contextReason
    rbacAllowed
    abacAllowed
    abacReason
    abacPolicy
    hybridStrategy
    policyDecision {
      name
      effect
      priority
      reason
    }
  }
}
```

This query is often the fastest way to see whether the real problem is:

- the user is missing a group assignment
- a contextual permission has no object context
- ABAC denied after RBAC allowed
- a policy override short-circuited the decision

## Case 20: Audit denied decisions in production

This final case is about operating the system safely.

A fintech team wants every denied permission decision to emit an audit event so
security staff can review unusual access patterns.

Enable permission auditing:

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_permission_audit": True,
        "permission_audit_log_all": False,
        "permission_audit_log_denies": True,
    }
}
```

When `role_manager.has_permission()` runs with auditing enabled, Rail Django
can emit permission-granted or permission-denied events through the security
event API.

This helps you answer production questions such as:

- which permission was denied
- which model and object were involved
- which roles the user had
- whether a policy matched
- which hybrid strategy produced the final decision

Always pair powerful access features with observability.

Otherwise, you will not know whether your rules are doing the right thing or
quietly blocking good traffic.

## A complete model example with roles, guards, and field rules

The individual cases are easier to understand after you see one model that
combines the main techniques in one place.

This example uses `GraphQLMeta` to keep the security design close to the
domain model:

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as RailGraphQLMeta


class Order(models.Model):
    customer = models.ForeignKey(
        "Customer",
        on_delete=models.PROTECT,
    )
    manager = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
    )
    department = models.CharField(max_length=100)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    card_token = models.CharField(max_length=255)

    @staticmethod
    def can_modify_order(user=None, instance=None, **kwargs):
        if user is None or instance is None:
            return False
        return instance.manager_id == user.id

    class GraphQLMeta(RailGraphQLMeta):
        access = RailGraphQLMeta.AccessControl(
            roles={
                "order_viewer": RailGraphQLMeta.Role(
                    name="order_viewer",
                    description="Read-only order access.",
                    role_type="functional",
                    permissions=["store.view_order"],
                ),
                "order_manager": RailGraphQLMeta.Role(
                    name="order_manager",
                    description="Manage assigned orders.",
                    role_type="business",
                    parent_roles=["order_viewer"],
                    permissions=[
                        "store.change_order",
                        "store.update_order_assigned",
                    ],
                ),
            },
            operations={
                "list": RailGraphQLMeta.OperationGuard(
                    roles=["order_viewer", "order_manager"],
                    permissions=["store.view_order"],
                ),
                "retrieve": RailGraphQLMeta.OperationGuard(
                    roles=["order_viewer", "order_manager"],
                    permissions=["store.view_order"],
                ),
                "update": RailGraphQLMeta.OperationGuard(
                    roles=["order_manager"],
                    permissions=["store.change_order"],
                    condition="can_modify_order",
                    match="all",
                    deny_message="Only the assigned manager can update this order.",
                ),
            },
            fields=[
                RailGraphQLMeta.FieldGuard(
                    field="card_token",
                    access="read",
                    visibility="hidden",
                    roles=["order_manager"],
                ),
                RailGraphQLMeta.FieldGuard(
                    field="total",
                    access="read",
                    visibility="visible",
                    roles=["order_viewer", "order_manager"],
                ),
            ],
        )
        classifications = RailGraphQLMeta.Classification(
            model=["customer-data"],
            fields={"card_token": ["secret"]},
        )
        abac_policies = [
            {
                "name": "same_department_only",
                "effect": "allow",
                "priority": 60,
                "subject_conditions": {
                    "department": {
                        "operator": "eq",
                        "target": "resource.department",
                    }
                },
            }
        ]
```

This model demonstrates a practical layering strategy:

- roles handle coarse job-based access
- operation guards handle model-specific workflows
- field guards handle sensitive fields
- ABAC handles department boundaries

That is the general pattern you want in most enterprise projects.

## A complete service-layer example with direct permission checks

You do not have to rely only on decorators.

Many teams prefer checking permissions inside service functions so the business
logic and the authorization decision live together.

This is a good fit when:

- several entry points call the same service
- you need a permission check before multiple database writes
- you want to unit test the service without building GraphQL resolver objects

Example:

```python
from django.core.exceptions import PermissionDenied
from rail_django.security import PermissionContext, role_manager


def approve_refund(*, user, refund):
    context = PermissionContext(
        user=user,
        object_instance=refund,
        operation="update",
    )

    if not role_manager.has_permission(
        user,
        "billing.approve_refund_assigned",
        context,
    ):
        raise PermissionDenied("You are not allowed to approve this refund.")

    refund.status = "approved"
    refund.save(update_fields=["status"])
    return refund
```

This approach stays simple and keeps your permission strings visible in the
business workflow.

## How to choose the hybrid strategy

The hybrid strategy determines how Rail Django combines RBAC and ABAC.

Choose it intentionally.

`rbac_and_abac`

- both systems must allow
- best for regulated or high-risk operations
- good default for finance, healthcare, and internal admin tools

`rbac_or_abac`

- either system can allow
- best for carefully controlled exception paths
- useful for break-glass or temporary incident workflows

`abac_override`

- ABAC wins even if RBAC disagrees
- useful only when your attribute rules are the real source of truth
- risky if your ABAC policies are broad

`rbac_then_abac`

- RBAC must allow first, then ABAC can still deny
- this is the safest general-purpose strategy
- good when roles define capability and ABAC narrows the scope

`most_restrictive`

- the most restrictive result wins
- behaves similarly to `rbac_and_abac` in the current engine
- useful when you want a conservative mental model

One current implementation detail is worth knowing.

If ABAC is enabled but no ABAC policy matches the request, the hybrid engine
falls back to the RBAC decision instead of applying a separate ABAC default
deny rule.

If you do not know which strategy to pick, start with `rbac_then_abac`.

## When to use the policy engine

The policy engine is not the same thing as ABAC.

ABAC evaluates structured subject, resource, environment, and action
attributes.

The policy engine evaluates explicit allow and deny rules with:

- roles
- permissions
- models
- fields
- operations
- classifications
- a custom callable condition

Use the policy engine for:

- platform-wide denials
- field masking overrides
- classification-based access
- emergency exceptions with clear priority order

Avoid using the policy engine for every normal CRUD rule.

RBAC is easier to maintain for the baseline.

## Classification tags for security-wide rules

Classifications let you group sensitive data by meaning instead of by model
name.

This is especially useful when many models contain the same category of
sensitive data.

Tag the model and fields:

```python
class Customer(models.Model):
    email = models.EmailField()
    national_id = models.CharField(max_length=32)
    annual_income = models.DecimalField(max_digits=12, decimal_places=2)

    class GraphQLMeta(RailGraphQLMeta):
        classifications = RailGraphQLMeta.Classification(
            model=["pii"],
            fields={
                "national_id": ["government-id"],
                "annual_income": ["financial"],
            },
        )
```

Apply policies against classifications:

```python
policy_manager.register_policy(
    AccessPolicy(
        name="deny_financial_fields_for_support",
        effect=PolicyEffect.DENY,
        priority=80,
        roles=["support_agent"],
        classifications=["financial"],
        reason="Support agents cannot access financial classifications.",
    )
)
```

This is one of the cleanest ways to scale field security across a large schema.

## Field permission behavior you should know

Field permissions in Rail Django are not only about "can read" and "cannot
read."

A field can be:

- visible
- hidden
- masked
- redacted

Access levels are separate from visibility:

- `none`
- `read`
- `write`
- `admin`

Important implementation detail:

- if no custom rule matches and the field name looks sensitive, Rail Django can
  mask it by default
- if no custom rule matches and the field is not sensitive, visibility usually
  falls back to visible
- write access can be restricted even when read access is allowed

That is why field-level security must be tested with both queries and mutation
inputs.

## Wildcards and pattern matching

Pattern behavior is useful, but you should understand the limits.

In RBAC effective permissions:

- exact permission names work
- `"*"` grants everything
- suffix wildcard permissions such as `"store.*"` work as prefix matches

In the policy engine and field permission engine:

- wildcard patterns use shell-style matching
- examples include `*token*`, `name*`, and `store.*`

Be careful not to assume that every subsystem uses the same wildcard rules.

If your security design depends on patterns, test the exact strings.

## Recommended rollout order

Permission systems fail when teams build them in the wrong order.

A reliable rollout order in Rail Django looks like this:

1. Keep generated Django model permissions enabled.
2. Register core business roles with `role_manager`.
3. Assign users through Django groups.
4. Add contextual `_own` and `_assigned` rules where needed.
5. Add `GraphQLMeta.OperationGuard` rules on models with special workflows.
6. Add field guards for sensitive values.
7. Add ABAC for tenant, department, environment, and risk boundaries.
8. Add policy overrides only for cross-cutting exceptions.
9. Turn on `explainPermission` during testing and review the output.
10. Turn on permission audit logging before production launch.

This sequence keeps the simple parts simple and reserves ABAC for the places
where it adds real value.

## Testing RBAC and ABAC rules

Permission bugs are easier to create than they are to notice.

Write tests for both allowed and denied paths.

A unit test for contextual RBAC can look like this:

```python
context = PermissionContext(user=user, object_instance=profile)
assert role_manager.has_permission(
    user,
    "accounts.update_profile_own",
    context,
) is True
```

An ABAC unit test can look like this:

```python
decision = abac_engine.evaluate(
    ABACContext(
        subject=AttributeSet(static_attributes={"department": "sales"}),
        resource=AttributeSet(static_attributes={"department": "sales"}),
    )
)

assert decision is not None
assert decision.allowed is True
```

An integration test can call the GraphQL explain query and assert:

- `rbacAllowed`
- `abacAllowed`
- `hybridStrategy`
- `reason`

If you skip denial tests, you will miss the cases that matter most.

## Common mistakes and how to avoid them

These are the most common design errors teams make when they first add ABAC
and RBAC to Rail Django.

Using RBAC for tenant boundaries

- bad because you end up creating one role per tenant
- fix it with ABAC and a tenant attribute comparison

Using ABAC for every normal CRUD permission

- bad because easy rules become harder to explain
- fix it by keeping normal capabilities in roles

Skipping `PermissionContext` for contextual permissions

- bad because `_own` and `_assigned` cannot evaluate correctly
- fix it by always passing the target instance or object ID

Forgetting field-level write restrictions

- bad because a user may update a protected field through mutation input
- fix it with field guards and `field_permission_input_mode`

Relying on undocumented exception policies

- bad because future maintainers will not know why access changes
- fix it by naming policies clearly and documenting the business reason

Choosing `rbac_or_abac` too early

- bad because a broad ABAC rule can bypass the normal role boundary
- fix it by starting with `rbac_then_abac`

## Troubleshooting denied access

When a user reports that a request was denied, work through the checks in this
order.

1. Confirm the user is authenticated.
2. Confirm the user has the expected Django group.
3. Confirm the group name matches the role name exactly.
4. Confirm the role was registered.
5. Confirm the role contains the expected permission string.
6. Confirm the permission string uses the right app label and model codename.
7. Confirm the resolver or service is checking the same permission string.
8. Confirm contextual permissions received a `PermissionContext`.
9. Confirm the context points at the right instance or object ID.
10. Confirm a policy override did not deny the request.
11. Confirm ABAC is enabled only when you intend it to be.
12. Confirm the hybrid strategy matches your mental model.
13. Confirm the ABAC policy actually matches the request attributes.
14. Confirm field rules are not hiding or masking the value afterward.
15. Run `explainPermission`.

That sequence will usually find the issue faster than reading code in random
order.

## Production design checklist

Before shipping a permission design, review it against this checklist.

- Every business capability has a clear permission name.
- Every role has a clear business description.
- No tenant boundary depends only on roles.
- Every `_own` and `_assigned` rule is backed by a real resolver path.
- High-risk operations use `match="all"` or a restrictive hybrid strategy.
- Sensitive fields have explicit field guards or classification policies.
- Break-glass paths are documented and audited.
- Permission denials are observable in production.
- The support team knows how to use `explainPermission`.
- Tests cover both the happy path and the denial path.

If you cannot explain one rule in a sentence, the rule is probably too
complicated.

## A compact reference of the most useful APIs

This section gives you one short reminder block per API.

`RoleDefinition`

- defines a named role
- holds description, role type, permissions, inheritance, and optional
  `max_users`

`role_manager.register_role()`

- registers a role definition
- also ensures a matching Django group exists when the app registry is ready

`role_manager.assign_role_to_user()`

- adds the user to the Django group
- invalidates cached permission decisions for that user

`PermissionContext`

- passes object, model, and runtime context into permission evaluation
- required for `_own` and `_assigned`

`require_role`

- checks role membership on a GraphQL resolver

`require_permission`

- checks one permission on a GraphQL resolver
- normalizes resolver arguments into a `PermissionContext`

`ABACPolicy`

- defines allow or deny logic over subject, resource, environment, and action
  attributes

`MatchCondition`

- defines the operator and comparison target
- can compare against a literal `value` or a dynamic `target`

`abac_manager.register_policy()`

- adds a reusable ABAC policy to the engine

`require_attributes`

- protects one resolver with inline ABAC conditions

`AccessPolicy`

- defines a policy-engine override with priority and effect

`GraphQLMeta.OperationGuard`

- protects generated model operations
- can require roles, permissions, authentication, and a condition callable

`GraphQLMeta.FieldGuard`

- controls field access level and visibility

`myPermissions`

- returns the authenticated user's broad capability matrix

`explainPermission`

- returns the detailed reason behind one specific permission decision

## Choosing between three valid designs

Sometimes the same business rule can be implemented in more than one way.

Here is a practical way to choose.

If the rule sounds like this:

"Every finance controller can approve refunds."

Use RBAC.

If the rule sounds like this:

"A finance controller can approve refunds only for the same region and only
during business hours."

Use hybrid RBAC plus ABAC.

If the rule sounds like this:

"Nobody in the contractor role may ever view fields classified as secret."

Use the policy engine or field policies.

Pick the simplest system that still matches the real business statement.

## One final end-to-end example

This example ties together the patterns from earlier sections in a realistic
workflow.

Imagine a regulated lending platform:

- loan officers can create applications
- underwriters can review assigned applications
- finance controllers can approve large loans
- contractors can never view bank account tokens
- only secure office requests can export approved loans

Setup:

```python
role_manager.register_role(
    RoleDefinition(
        name="loan_officer",
        description="Create loan applications.",
        role_type=RoleType.BUSINESS,
        permissions=["lending.add_application", "lending.view_application"],
    )
)

role_manager.register_role(
    RoleDefinition(
        name="underwriter",
        description="Review assigned applications.",
        role_type=RoleType.BUSINESS,
        permissions=[
            "lending.view_application",
            "lending.update_application_assigned",
        ],
    )
)

role_manager.register_role(
    RoleDefinition(
        name="finance_controller",
        description="Approve large regulated loans.",
        role_type=RoleType.BUSINESS,
        permissions=[
            "lending.view_application",
            "lending.approve_application",
        ],
    )
)
```

Cross-cutting secret-field denial:

```python
policy_manager.register_policy(
    AccessPolicy(
        name="deny_account_tokens_for_contractors",
        effect=PolicyEffect.DENY,
        priority=100,
        roles=["contractor"],
        fields=["*account_token*"],
        reason="Contractors cannot access bank account tokens.",
    )
)
```

Environment restriction for exports:

```python
@require_attributes(
    subject_conditions={
        "roles": {
            "operator": "intersects",
            "value": ["finance_controller"],
        }
    },
    environment_conditions={
        "is_secure": {
            "operator": "eq",
            "value": True,
        }
    },
)
def resolve_export_approved_loans(root, info):
    ...
```

Assigned review workflow:

```python
def review_application(user, application):
    context = PermissionContext(
        user=user,
        object_instance=application,
        operation="update",
    )
    if not role_manager.has_permission(
        user,
        "lending.update_application_assigned",
        context,
    ):
        raise PermissionDenied("This application is not assigned to you.")
```

Large-loan ABAC overlay:

```python
abac_manager.register_policy(
    ABACPolicy(
        name="large_loan_same_region",
        effect="allow",
        priority=70,
        subject_conditions={
            "roles": MatchCondition(
                ConditionOperator.INTERSECTS,
                value=["finance_controller"],
            )
        },
        resource_conditions={
            "amount": MatchCondition(
                ConditionOperator.GTE,
                value=500000,
            )
        },
    )
)
```

The key lesson is not that you should copy this exact design.

The key lesson is that each layer has one clear responsibility:

- roles define business capability
- contextual RBAC narrows capability to one object
- ABAC narrows capability to runtime attributes
- policies define platform-wide exceptions
- field guards protect sensitive values

## Summary

RBAC is the backbone of most Rail Django permission systems.

ABAC is the precision layer that keeps data access scoped to the right tenant,
department, time window, network, or risk profile.

The policy engine is the override layer for platform-wide exceptions.

Field permissions protect values after model-level access succeeds.

Hybrid evaluation lets you combine role capability with runtime conditions
without inventing thousands of roles.

If you keep those responsibilities separate, your permission design stays
understandable.

If you mix them carelessly, you will eventually end up with a system that
nobody can safely change.

## Next steps

Continue with these pages after you finish this tutorial:

- [Authentication tutorial](./authentication.md)
- [Permissions and RBAC](../security/permissions.md)
- [RBAC system](../library/security/rbac.md)
- [ABAC system](../library/security/abac.md)
- [Hybrid RBAC + ABAC](../library/security/hybrid.md)
- [Security reference](../reference/security.md)
