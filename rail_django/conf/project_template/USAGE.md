# Rail Django Usage Guide

Welcome to **Rail Django**, a production-ready wrapper around Django and Graphene designed to accelerate GraphQL API development.

## 📚 Table of Contents

1.  [Getting Started](#1-getting-started)
2.  [Core Concepts](#2-core-concepts)
3.  [Configuration](#3-configuration)
4.  [Security](#4-security)
5.  [Advanced Features](#5-advanced-features)
    - [Multi-Schema Setup](#multi-schema-setup)
    - [PDF Templating](#pdf-templating)
6.  [Deployment](#6-deployment)

---

## 1. Getting Started

### Installation

Ensure you have Python 3.8+ installed.

```bash
pip install git+https://github.com/raillogistic/rail-django.git
```

### Creating a Project

Use the CLI to bootstrap a new project with the recommended structure.

```bash
rail-admin startproject my_project
cd my_project
```

### Starting the Server

Run the development server (Docker is recommended for full stack, but local works too):

```bash
python manage.py migrate
python manage.py runserver
```

Visit `http://localhost:8000/graphql` (or your configured endpoint) to see the API.

---

## 2. Core Concepts

### Auto-Generated Schema

Rail Django automatically inspects your Django models and generates:

- **Types**: GraphQL types with all model fields.
- **Queries**: `list` and `retrieve` operations with filtering, ordering, and pagination.
- **Mutations**: `create`, `update`, and `delete` operations.

**Example Model (`apps/blog/models.py`):**

```python
from django.db import models

class Post(models.Model):
    title = models.CharField(max_length=100)
    content = models.TextField()
```

**Resulting GraphQL API:**

- Query: `post(id: ID!)`, `posts(title_Icontains: String)`
- Mutation: `createPost`, `updatePost`, `deletePost`

### Customizing Generation

You can control what gets generated via `settings.py` or decorators.

**Exclude a specific model:**

```python
# settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "excluded_models": ["auth.Group", "blog.SecretData"],
    }
}
```

---

## 3. Configuration

Configuration is split into three levels:

1.  **Global Defaults**: Defined by the library.
2.  **Project Global**: `RAIL_DJANGO_GRAPHQL` in `settings.py`.
3.  **Schema Specific**: `RAIL_DJANGO_GRAPHQL_SCHEMAS` in `settings.py`.

### Key Settings (`RAIL_DJANGO_GRAPHQL`)

- `schema_settings`: Controls introspection, auth requirements, and model exclusion.
- `query_settings`: Configures pagination (Relay/Offset), filtering.
- `mutation_settings`: Toggles CRUD generation.
- `security_settings`: Rate limiting, depth limiting.

See `settings/base.py` for the full annotated list of options.

---

## 4. Security

Rail Django is secure by default.

### Authentication

- **JWT Default**: The template comes with JWT authentication pre-configured.
- **Auth Schema**: Use the `auth` schema for public login/register endpoints.
- **Secure API**: The `default` schema requires a valid `Authorization: Bearer <token>` header.

### RBAC (Role-Based Access Control)

Control access to specific resources:

```python
from rail_django.security import require_role

@require_role("admin")
def resolve_sensitive_data(root, info):
    return "Secret"
```

### Production Hardening

- **Introspection**: Disabled by default in production.
- **GraphiQL**: Disabled by default in production.
- **Depth Limit**: Queries deeper than 10 levels are rejected.

---

## 5. Advanced Features

### Multi-Schema Setup

You can run multiple GraphQL endpoints with different configurations.

**Configuration in `settings.py`:**

```python
RAIL_DJANGO_GRAPHQL_SCHEMAS = {
    "auth": {
        "schema_settings": { "authentication_required": False },
        "mutation_settings": { "generate_create": False }
    },
    "default": {
        "schema_settings": { "authentication_required": True }
    }
}
```

**Usage:**

- `/api/auth/` -> Open endpoint for login.
- `/api/graphql/` -> Secured endpoint for data.

### PDF Templating

Generate PDFs from your models using `WeasyPrint`.

1.  **Configure**: Set defaults in `RAIL_DJANGO_GRAPHQL_TEMPLATING`.
2.  **Decorate**: Add `@model_pdf_template` to your model method.

```python
from rail_django.extensions.templating import model_pdf_template

class Invoice(models.Model):
    @model_pdf_template(
        content="pdf/invoice.html",
        url="invoices/print"
    )
    def print_invoice(self):
        return {"total": self.amount}
```

3.  **Access**: `GET /api/templates/invoices/print/<pk>/`

---

## 6. Deployment

### Docker (Recommended)

The project includes a production-ready `docker-compose.yml`.

1.  **Configure**: Copy `.env.example` to `.env` and set secrets.
2.  **Build**: `docker-compose -f deploy/docker/docker-compose.yml up -d --build`
3.  **Nginx**: A pre-configured Nginx container handles static files and reverse proxying.

### Manual Deployment

See `deploy/USAGE.md` for detailed manual deployment steps (HTTPS, Database connection, etc.).
