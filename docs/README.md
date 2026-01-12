# Rail Django Documentation

Rail Django is a GraphQL framework built on Django and Graphene. These docs cover
how to run the framework, how to use the GraphQL and REST APIs, and how the
internals are structured.

## Quick start

1. Install the package

```bash
pip install rail-django
```

2. Add apps to `INSTALLED_APPS`

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "graphene_django",
    "django_filters",
    "corsheaders",
    "rail_django",
    "rail_django.core",
    "rail_django.generators",
    "rail_django.extensions",
]
```

3. Add the library URLs

```python
from django.urls import include, path

urlpatterns = [
    path("", include("rail_django.urls")),
]
```

4. Configure `RAIL_DJANGO_GRAPHQL` (see `configuration.md`)

5. Run the server and open:
- `http://localhost:8000/graphql/gql/` (primary API)
- `http://localhost:8000/graphql/graphiql/` (if enabled)

## Documentation map

- `graphql.md`: GraphQL API usage and examples
- `rest-api.md`: REST endpoints and health APIs
- `configuration.md`: Settings reference and examples
- `security.md`: Auth, RBAC, and security controls
- `extensions.md`: Built-in extensions (health, export, templating, MFA)
- `architecture.md`: Internal architecture and request lifecycle
- `modules.md`: Codebase map for contributors
- `testing.md`: Testing strategy and test utilities
- `cli.md`: CLI and management commands

## Conventions

- Default GraphQL field names are snake_case (`auto_camelcase = False`).
- If you enable `auto_camelcase`, field names are exposed in camelCase.
- Multi-schema endpoints live at `/graphql/<schema_name>/`.
