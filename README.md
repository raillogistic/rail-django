# Rail Django

Rail Django is a production-ready GraphQL framework for Django, built on top of Graphene-Django. It reduces boilerplate, enforces security best practices, and provides enterprise-grade features out of the box.

## 🚀 Key Features

*   **Auto-Generation**: GraphQL Types, Queries, and Mutations generated from Django Models.
*   **Performance**: Solves N+1 problems automatically with `select_related`/`prefetch_related` injection.
*   **Security**: Built-in RBAC, Query Depth Limiting, and Input Validation.
*   **Developer Experience**: `auto_camelCase` conversion, CLI scaffolding, and clear configuration.
*   **Enterprise Extensions**: Audit Logging, Webhooks, Exporting, and Observability.

## 📚 Documentation

Full documentation is available in the `rail_django/docs/` directory.

*   [**Getting Started**](rail_django/docs/getting-started/quickstart.md): Installation and your first API.
*   [**Core Concepts**](rail_django/docs/core/queries.md): Queries, Mutations, and Filtering.
*   [**Security**](rail_django/docs/security/permissions.md): Authentication, RBAC, and Validation.
*   [**Advanced Guides**](rail_django/docs/guides/testing.md): Testing, Plugins, and Troubleshooting.
*   [**Extensions**](rail_django/docs/extensions/index.md): Audit Logging, Webhooks, and Multitenancy.
*   [**Reference**](rail_django/docs/reference/api.md): API and CLI reference.

## 📦 Installation

```bash
pip install rail-django
```

## ⚡ Quickstart

```bash
# Create a new project
rail-admin startproject my_api
cd my_api

# Setup database
python manage.py migrate
python manage.py createsuperuser

# Run server
python manage.py runserver
```

Go to `http://localhost:8000/graphql` to explore your API.

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to get involved.

## 📝 License

MIT
## Generated ModelForm Rollout Notes

Generated ModelForm contract mode is enabled by default and does not replace
existing `formConfig` consumers automatically.

### Backend controls

- Override per model via `GraphQLMeta.custom_metadata`:

```python
class Product(models.Model):
    class GraphQLMeta(RailGraphQLMeta):
        custom_metadata = {
            "generated_form": {
                "enabled": False,  # explicit per-model disable
            }
        }
```

- Optional settings-level exclusion (`settings.py`):

```python
RAIL_DJANGO_FORM = {
    "generated_form_excluded_models": ["test_app.Product"],
}
```

### Compatibility and migration

- `modelFormContract`, `modelFormContractPages`, and `modelFormInitialData` are
  available for all models except explicitly excluded ones.
- Legacy `formConfig` remains available and should be used as fallback when
  generated mode is explicitly disabled.
- Canonical mutation names remain unchanged: `create<Model>`, `update<Model>`,
  `bulkCreate<Model>`, `bulkUpdate<Model>`.
