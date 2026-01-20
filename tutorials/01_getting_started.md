# Tutorial 1: Getting Started with Rail Django

Welcome to the **Rail Django** tutorial series! In this first guide, we will cover the installation process, initial configuration, and running your first GraphQL query.

## What is Rail Django?

Rail Django is a batteries-included framework built on top of `graphene-django`. It automates the boring parts of building GraphQL APIs—like creating types, filters, and CRUD mutations—while providing enterprise-grade features like Audit Logging, RBAC, and Webhooks out of the box.

## 1. Installation

First, install the package using pip:

```bash
pip install rail-django
```

You also need to install the dependencies for features you plan to use. For a standard setup:

```bash
pip install "rail-django[standard]"
```

## 2. Project Setup

We assume you have a standard Django project. If not, create one:

```bash
django-admin startproject myproject
cd myproject
python manage.py startapp myapp
```

### Configure `INSTALLED_APPS`

Add `rail_django` and required apps to your `settings.py`:

```python
# myproject/settings.py

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Rail Django dependencies
    "graphene_django",
    "django_filters",
    "corsheaders",

    # The library itself
    "rail_django",

    # Your app
    "myapp",
]
```

### Middleware Configuration

Add the necessary middleware:

```python
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware", # Recommended for frontend access
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    
    # Rail Django Middleware (Optional but recommended for full features)
    "rail_django.core.middleware.RailGraphQLMiddleware",
]
```

### URL Configuration

Wire up the GraphQL endpoint in `myproject/urls.py`:

```python
# myproject/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    # Mounts GraphQL at /graphql/
    path("", include("rail_django.urls")), 
]
```

## 3. Basic Configuration

Rail Django uses a single dictionary for configuration. Add this to `settings.py`:

```python
# myproject/settings.py

RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "enable_graphiql": True,        # Enable the interactive IDE
        "enable_introspection": True,   # Allow schema inspection
    },
    "query_settings": {
        "default_page_size": 20,
    }
}
```

## 4. Your First Model

Let's define a simple model in `myapp/models.py`. The magic happens with the `GraphQLMeta` inner class.

```python
# myapp/models.py
from django.db import models
from rail_django.models import GraphQLMetaConfig

class Book(models.Model):
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=100)
    published_date = models.DateField()

    class GraphQLMeta(GraphQLMetaConfig):
        # This empty config enables:
        # 1. Type generation
        # 2. List & Detail queries (books, book)
        # 3. Filtering & Ordering
        # 4. CRUD Mutations (create_book, update_book, delete_book)
        pass
```

Run migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

## 5. Running the Server

Start the development server:

```bash
python manage.py runserver
```

Open your browser to `http://127.0.0.1:8000/graphql/`. You should see the GraphiQL interface.

## 6. Your First Query

Try fetching the books (the list will be empty):

```graphql
query {
  books {
    id
    title
    author
  }
}
```

Now, let's create a book using the auto-generated mutation:

```graphql
mutation {
  create_book(input: {
    title: "The Django Guide",
    author: "Rail Team",
    published_date: "2024-01-01"
  }) {
    object {
      id
      title
    }
    errors {
      message
    }
  }
}
```

Query the list again, and you'll see your new book!

## Next Steps

In the [next tutorial](./02_models_and_schema.md), we will dive deeper into `GraphQLMeta` to control exactly how your models are exposed.
