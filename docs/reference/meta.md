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

## Tenant field

Multi-tenancy can use GraphQLMeta to declare which field identifies the tenant
for a model. Set `tenant_field` to the field name (or a Django path such as
`organization__tenant`). Set it to `None` or an empty value to opt the model out
of tenant scoping.

```python
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig


class Project(models.Model):
    name = models.CharField(max_length=200)
    organization = models.ForeignKey("org.Organization", on_delete=models.CASCADE)

    class GraphQLMeta(GraphQLMetaConfig):
        tenant_field = "organization"
```

## YAML meta files

You can declare the same GraphQLMeta configuration in `meta.yaml` at the root
of any app. The loader scans installed apps at startup and applies the YAML
configuration to models that do not define a `GraphQLMeta` inner class. It also
supports `meta.json` for backward compatibility.

The YAML/JSON file accepts the same config sections you would define in code:
`filtering`, `fields`, `ordering`, `resolvers`, `access`, and
`classifications` (plus legacy keys like `include_fields`, `custom_filters`,
`custom_resolvers`, `filter_fields`, and `quick_filter_fields`).

Full example (`apps/store/meta.yaml`):

```yaml
roles:
  catalog_viewer:
    description: Read-only access
    role_type: functional
    permissions:
      - store.view_product
  catalog_editor:
    description: Create and update catalog entries
    role_type: business
    permissions:
      - store.add_product
      - store.change_product
    parent_roles:
      - catalog_viewer
  catalog_admin:
    description: Full control over catalog data
    role_type: system
    permissions:
      - store.*
    parent_roles:
      - catalog_editor
    is_system_role: true
    max_users: 5
models:
  store.Product:
    fields:
      include:
        - id
        - name
        - sku
        - price
        - status
        - created_at
        - updated_at
      exclude:
        - internal_notes
      read_only:
        - created_at
        - updated_at
      write_only:
        - internal_token
    filtering:
      quick:
        - name
        - category__name
      quick_lookup: icontains
      auto_detect_quick: false
      fields:
        status:
          lookups:
            - eq
            - in
          choices:
            - draft
            - active
          help_text: Product status
        created_at:
          - gte
          - lte
      custom:
        has_discount: store.graphql_filters.filter_has_discount
    ordering:
      allowed:
        - name
        - created_at
        - price
      default:
        - -created_at
      allow_related: true
    resolvers:
      queries:
        featured: store.graphql_resolvers.resolve_featured_products
      mutations:
        apply_discount: store.graphql_resolvers.mutate_apply_discount
      fields:
        display_name: store.graphql_resolvers.resolve_display_name
    access:
      operations:
        list:
          roles:
            - catalog_viewer
          require_authentication: true
        retrieve:
          permissions:
            - store.view_product
          condition: store.graphql_guards.can_access_product
          match: all
          deny_message: You cannot view this product.
        create:
          roles:
            - catalog_editor
          permissions:
            - store.add_product
          match: all
        update:
          roles:
            - catalog_editor
          condition: store.graphql_guards.can_update_product
        delete:
          roles:
            - catalog_admin
          deny_message: Only admins can delete products.
        bulk_update:
          roles:
            - catalog_admin
        "*":
          roles:
            - staff
      fields:
        - field: cost_price
          access: read
          visibility: masked
          mask_value: "***"
          roles:
            - catalog_admin
        - field: supplier_email
          access: read
          visibility: hidden
          permissions:
            - store.view_supplier_pii
          condition: store.graphql_guards.can_view_supplier_email
    classifications:
      model:
        - inventory
      fields:
        cost_price:
          - financial
        supplier_email:
          - pii
  store.Category:
    include_fields:
      - id
      - name
      - slug
    exclude_fields:
      - internal_notes
    quick_filter_fields:
      - name
    filters:
      quick:
        - name
    filter_fields:
      name:
        - exact
        - icontains
      created_at:
        - gte
        - lte
    custom_filters:
      starts_with: store.graphql_filters.filter_category_starts_with
    custom_resolvers:
      list: store.graphql_resolvers.resolve_category_list
```

Notes:
- Use `models` to map model names (or `app_label.Model`) to GraphQLMeta configs.
- Dotted paths in `custom`, `resolvers`, guard `condition`, or legacy `custom_*`
  values are imported as callables. Non-dotted strings are treated as model methods.
- Legacy keys (`include_fields`, `custom_filters`, `custom_resolvers`,
  `filter_fields`, `quick_filter_fields`, `filters`) are supported for backward
  compatibility and can be used instead of the structured sections.
- When `roles` is present at the top level, the file must use `models` for
  model configs (top-level model entries are not parsed).
- If a model defines `GraphQLMeta` in code, it takes precedence over file-based meta.
- If both `meta.yaml` and `meta.json` are present, `meta.yaml` is used.

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
limit operators per field, and `quick` to define a text search across fields.

```python
from django.utils import timezone


class GraphQLMeta(GraphQLMetaConfig):
    filtering = GraphQLMetaConfig.Filtering(
        quick=["name", "owner__email", "account__name"],
        quick_lookup="icontains",
        auto_detect_quick=False,
        fields={
            "status": GraphQLMetaConfig.FilterField(
                lookups=["eq", "in"],
                choices=["draft", "active", "archived"],
                help_text="Project status",
            ),
            "created_at": GraphQLMetaConfig.FilterField(lookups=["gte", "lte"]),
        },
        custom={
            "has_overdue_tasks": "filter_has_overdue_tasks",
        },
        presets={
            "overdue": {"has_overdue_tasks": True},
            "active": {"status": {"eq": "active"}},
            "priority": {
                "AND": [
                    {"status": {"eq": "active"}},
                    {"has_overdue_tasks": True}
                ]
            },
        },
        computed_filters={
            "profit_margin": {
                "expression": "expression_object", # Django Expression
                "filter_type": "float",
                "description": "Calculated profit margin"
            }
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
- Custom filter callables must accept `(queryset, name, value)` for legacy
  django-filter inputs (Relay or flat filter style).
- Use `@staticmethod` (or a standalone function) for custom filters.
- The default `where` input uses nested operators (for example:
  `status: { in: [...] }`, `created_at: { gte: ... }`).
- The legacy `filters` input (when enabled) follows django-filter naming such as
  `status__in` or `created_at__gte`.
- The `lookups` list accepts nested operator names and is mapped to django
  lookups when using the legacy flat filters.
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

## Mutation Pipeline

Use `GraphQLMetaConfig.Pipeline` to customize the mutation pipeline for a model.
The pipeline architecture provides composable, testable mutation handling.

### Enabling the Pipeline Backend

First, enable the pipeline backend in your settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        "mutation_backend": "pipeline",  # "legacy" for closure-based (default)
    }
}
```

### Customizing the Pipeline

You can customize the pipeline per-model using GraphQLMeta:

```python
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig
from rail_django.generators.pipeline.base import MutationStep


class InventoryCheckStep(MutationStep):
    """Custom step to check inventory before order creation."""
    order = 75  # After validation, before execution
    name = "inventory_check"

    def execute(self, ctx):
        # Check inventory availability
        product_id = ctx.input_data.get("product")
        quantity = ctx.input_data.get("quantity", 1)
        # ... validation logic ...
        return ctx


class Order(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()

    class GraphQLMeta(GraphQLMetaConfig):
        pipeline = GraphQLMetaConfig.Pipeline(
            # Add custom steps to all mutation types
            extra_steps=[InventoryCheckStep],

            # Skip specific steps by name
            skip_steps=["audit"],

            # Custom step ordering
            step_order={"validation": 50},

            # Operation-specific steps
            create_steps=[OrderNumberGenerationStep],
            update_steps=[],
            delete_steps=[RefundProcessingStep],
        )
```

### Available Pipeline Steps

The default pipeline includes these steps (in order):

| Order | Step Name | Description |
|-------|-----------|-------------|
| 10 | `authentication` | Verify user is authenticated |
| 20 | `model_permission` | Check Django model permissions |
| 25 | `operation_guard` | Check GraphQLMeta operation guards |
| 30 | `sanitization` | Sanitize input data |
| 35 | `instance_lookup` | Look up instance (update/delete only) |
| 40 | `enum_normalization` | Convert GraphQL enums to Django values |
| 45 | `dual_field_processing` | Handle nested_X vs X field priority |
| 48 | `read_only_filter` | Remove read-only fields from input |
| 49 | `created_by` | Auto-populate created_by field (create only) |
| 50 | `tenant_injection` | Inject tenant fields |
| 60 | `input_validation` | Run input validator |
| 65 | `nested_limit_validation` | Validate nested operation limits |
| 70 | `nested_data_validation` | Validate nested data structure |
| 80 | `create_execution` / `update_execution` / `delete_execution` | Execute mutation |
| 90 | `audit` | Log to audit system |

### Creating Custom Steps

Create custom steps by extending `MutationStep`:

```python
from rail_django.generators.pipeline.base import MutationStep
from rail_django.generators.pipeline.context import MutationContext


class NotificationStep(MutationStep):
    """Send notification after successful mutation."""
    order = 85  # After execution, before audit
    name = "notification"

    def should_run(self, ctx: MutationContext) -> bool:
        # Only run for successful operations
        return super().should_run(ctx) and ctx.result is not None

    def execute(self, ctx: MutationContext) -> MutationContext:
        from myapp.notifications import send_notification

        send_notification(
            user=ctx.user,
            action=ctx.operation,
            model=ctx.model_name,
            instance=ctx.result,
        )
        return ctx
```

### Operation-Filtered Steps

For steps that only apply to specific operations:

```python
from rail_django.generators.pipeline.base import OperationFilteredStep


class OrderConfirmationStep(OperationFilteredStep):
    """Send order confirmation on create only."""
    allowed_operations = ("create",)
    order = 85
    name = "order_confirmation"

    def execute(self, ctx):
        # Send confirmation email
        return ctx
```

## Legacy names

GraphQLMeta still accepts legacy attribute names:
- `include_fields`, `exclude_fields`
- `filters`, `filter_fields`, `quick_filter_fields`
- `custom_filters`

Prefer the structured config classes in new code.
