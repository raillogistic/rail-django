# Quick Start

Use these steps to get Rail Django running locally.

## Install the package

```bash
pip install rail-django
```

## Add apps to `INSTALLED_APPS`

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
]
```

## Add the library URLs

```python
from django.urls import include, path

urlpatterns = [
    path("", include("rail_django.urls")),
]
```

## Configure `RAIL_DJANGO_GRAPHQL`

See [configuration](../reference/configuration.md) for the full settings map.

## Run the server

The GraphQL endpoints are:

- `http://localhost:8000/graphql/` (default schema)
- `http://localhost:8000/graphql/<schema_name>/` (multi-schema)

GraphiQL is served on the same endpoint when `schema_settings.enable_graphiql`
is enabled. If you register a dedicated `graphiql` schema, it will be available
at `http://localhost:8000/graphql/graphiql/`.
