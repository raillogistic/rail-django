# Quickstart Guide

This tutorial will guide you through creating a new Rail Django project, defining a model, and querying it via GraphQL.

## 1. Create a Project

Rail Django includes a CLI tool `rail-admin` (similar to `django-admin`) that scaffolds a project with optimal defaults and directory structure.

```bash
rail-admin startproject my_api
cd my_api
```

This creates a project structure like this:

```text
my_api/
├── manage.py
├── my_api/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── apps/
    └── __init__.py
```

## 2. Setup Database

Initialize the database and create a superuser for accessing the Django Admin.

```bash
python manage.py migrate
python manage.py createsuperuser
```

## 3. Create an App

Create a new app inside the `apps/` directory.

```bash
python manage.py startapp blog apps/blog
```

Add the app to `INSTALLED_APPS` in `my_api/settings.py`:

```python
INSTALLED_APPS = [
    # ...
    "rail_django",
    "apps.blog",
]
```

## 4. Define a Model

Edit `apps/blog/models.py` to define a simple `Post` model.

```python
from django.db import models

class Post(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Rail Django uses this to enable GraphQL features
        app_label = "blog" 
```

Now, make migrations and migrate:

```bash
python manage.py makemigrations
python manage.py migrate
```

## 5. Enable GraphQL

Rail Django automatically discovers models, but explicit registration provides more control. Create a `schema.py` in your app `apps/blog/schema.py` (optional for simple cases if using auto-discovery, but recommended).

For now, Rail Django's auto-discovery will likely pick it up if you haven't customized the registry.

## 6. Run the Server

```bash
python manage.py runserver
```

Open your browser to `http://127.0.0.1:8000/graphql`.

## 7. Query Your Data

You can now query your API. Notice that `created_at` automatically becomes `createdAt` (camelCase).

```graphql
query {
  posts {
    id
    title
    content
    createdAt
  }
}
```

You can also use the plural alias:

```graphql
query {
  allPosts {
    title
  }
}
```

## Next Steps

*   Learn about **[Configuration](../core/configuration.md)** to tweak settings.
*   Explore **[Models & Schema](../core/models-and-schema.md)** to see how to customize fields.