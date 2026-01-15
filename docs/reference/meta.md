# GraphQLMeta

GraphQLMeta is the per-model configuration class defined in
`rail_django/core/meta.py`. It controls how Rail Django generates GraphQL
types, filters, ordering, and access guards for a Django model.

## Define GraphQLMeta on a model

Define GraphQLMeta as an inner class on your model. The generator looks for
`GraphQLMeta` or `GraphqlMeta` on the model class.

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig


class Project(models.Model):
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class GraphQLMeta(GraphQLMetaConfig):
        fields = GraphQLMetaConfig.Fields(
            include=["id", "name", "status", "created_at"],
            read_only=["status"],
        )
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "created_at"],
            default=["-created_at"],
        )
```

Notes:
- This is not Django's `class Meta`.
- The config is cached per process. Restart the server after changes.

## Field exposure

Use `GraphQLMetaConfig.Fields` to control which model fields are visible.

```python
class GraphQLMeta(GraphQLMetaConfig):
    fields = GraphQLMetaConfig.Fields(
        exclude=["internal_notes", "cost_price"],
        read_only=["status", "created_at"],
        write_only=["secret_token"],
    )
```

Field rules:
- `include`: allowlist; when set, only those fields are exposed.
- `exclude`: removes fields from both queries and mutation inputs.
- `read_only`: exposed in queries only (removed from mutation inputs).
- `write_only`: exposed in mutation inputs only (hidden from object types).

## Filtering and quick search

Filtering settings live under `GraphQLMetaConfig.Filtering`. Use `fields` to
limit lookups per field, and `quick` to define a text search across fields.

```python
from django.utils import timezone


class GraphQLMeta(GraphQLMetaConfig):
    filtering = GraphQLMetaConfig.Filtering(
        quick=["name", "owner__email", "account__name"],
        quick_lookup="icontains",
        auto_detect_quick=False,
        fields={
            "status": GraphQLMetaConfig.FilterField(
                lookups=["exact", "in"],
                choices=["draft", "active", "archived"],
                help_text="Project status",
            ),
            "created_at": GraphQLMetaConfig.FilterField(lookups=["gte", "lte"]),
        },
        custom={
            "has_overdue_tasks": "filter_has_overdue_tasks",
        },
    )

    @staticmethod
    def filter_has_overdue_tasks(queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            tasks__due_at__lt=timezone.now(),
            tasks__is_done=False,
        ).distinct()
```

Filtering notes:
- Custom filter callables must accept `(queryset, name, value)`.
- Use `@staticmethod` (or a standalone function) for custom filters.
- Filter input names follow django-filter naming such as `status__in` or
  `created_at__gte`.
- The quick filter is exposed as the `quick` argument on list queries.

## Ordering

Use `GraphQLMetaConfig.Ordering` to limit and default ordering.

```python
class GraphQLMeta(GraphQLMetaConfig):
    ordering = GraphQLMetaConfig.Ordering(
        allowed=["name", "created_at", "owner__email"],
        default=["-created_at"],
        allow_related=True,
    )
```

Ordering notes:
- `allowed` is an allowlist for `order_by`.
- `default` is used when no client ordering is provided.
- Use `-` prefix for descending order (for example `-created_at`).

## Access control

Use `GraphQLMetaConfig.AccessControl` to define roles, operation guards, and
field guards.

### Operation guards

Operation guards are checked by auto-generated list, retrieve, create, update,
delete, bulk, and subscription operations. Method mutations also enforce an
operation guard inferred from the method name (or action kind) on the target
instance.

```python
class GraphQLMeta(GraphQLMetaConfig):
    access = GraphQLMetaConfig.AccessControl(
        roles={
            "billing_admin": GraphQLMetaConfig.Role(
                description="Billing admins",
                permissions=["billing.view_invoice", "billing.change_invoice"],
            ),
        },
        operations={
            "list": GraphQLMetaConfig.OperationGuard(roles=["billing_admin"]),
            "retrieve": GraphQLMetaConfig.OperationGuard(
                permissions=["billing.view_invoice"]
            ),
            "update": GraphQLMetaConfig.OperationGuard(
                permissions=["billing.change_invoice"],
                condition="can_update_invoice",
                match="all",
                deny_message="Invoice updates are restricted.",
            ),
            "delete": GraphQLMetaConfig.OperationGuard(roles=["billing_admin"]),
            "bulk_update": GraphQLMetaConfig.OperationGuard(roles=["billing_admin"]),
            "*": GraphQLMetaConfig.OperationGuard(roles=["staff"]),
        },
    )

    @staticmethod
    def can_update_invoice(user, operation, info, instance, model):
        if not instance:
            return False
        return user.is_staff and not instance.is_locked
```

Guard notes:
- `allow_anonymous` and `require_authentication` can override auth checks.
- `match="all"` requires every rule (roles, permissions, condition) to pass.
- Use `*` to define a fallback guard for all operations.
- Bulk mutations enforce both the base operation guard and the `bulk_*` guard.
- Nested create/update/connect operations apply related-model guards (`create`, `update`, `retrieve`) for touched models.

### Field guards

Field guards register field-level visibility and access rules.

```python
class Customer(models.Model):
    email = models.EmailField()
    ssn = models.CharField(max_length=32)
    credit_card = models.CharField(max_length=32)

    class GraphQLMeta(GraphQLMetaConfig):
        access = GraphQLMetaConfig.AccessControl(
            fields=[
                GraphQLMetaConfig.FieldGuard(
                    field="credit_card",
                    access="read",
                    visibility="masked",
                    mask_value="****",
                    roles=["billing_admin"],
                ),
                GraphQLMetaConfig.FieldGuard(
                    field="ssn",
                    access="read",
                    visibility="hidden",
                    roles=["billing_admin"],
                ),
                GraphQLMetaConfig.FieldGuard(
                    field="email",
                    access="read",
                    visibility="visible",
                    condition="can_view_email",
                ),
            ],
        )

        @staticmethod
        def can_view_email(context):
            return context.user.is_staff or (
                context.instance and context.instance.id == context.user.id
            )
```

Field guard notes:
- `access` values: `none`, `read`, `write`, `admin`.
- `visibility` values: `visible`, `hidden`, `masked`, `redacted`.
- Field guard conditions receive a `FieldContext` object.

## Classification tags

Classification tags let you group fields for policy rules.

```python
class GraphQLMeta(GraphQLMetaConfig):
    classifications = GraphQLMetaConfig.Classification(
        model=["pii"],
        fields={
            "email": ["pii"],
            "salary": ["financial"],
        },
    )
```

See `docs/reference/security.md` for policy configuration.

## Legacy names

GraphQLMeta still accepts legacy attribute names:
- `include_fields`, `exclude_fields`
- `filters`, `filter_fields`, `quick_filter_fields`
- `custom_filters`

Prefer the structured config classes in new code.
