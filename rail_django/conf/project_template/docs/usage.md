# Rail Django - Complete Usage Guide

Welcome to the **Rail Django** documentation, the production framework for building enterprise GraphQL APIs with Django.

---

## 📖 Overview

Rail Django simplifies GraphQL API development by automating schema generation, CRUD mutations, and integrating enterprise-ready features out of the box.

### Philosophy

1. **Convention over Configuration** - Define a Django model, get a working API immediately.
2. **Security by Default** - Permissions, depth limits, and input validation enabled by default.
3. **Batteries Included** - Built-in audit, exports, webhooks, and health monitoring.

---

## 📑 Table of Contents

### Getting Started

| Guide                                             | Description                              |
| ------------------------------------------------- | ---------------------------------------- |
| [Installation](./getting-started/installation.md) | Prerequisites and framework installation |
| [Quickstart](./getting-started/quickstart.md)     | Create your first project in 5 minutes   |

### Security

| Guide                                              | Description                                  |
| -------------------------------------------------- | -------------------------------------------- |
| [JWT Authentication](./security/authentication.md) | Login, tokens, cookies, and sessions         |
| [Permissions & RBAC](./security/permissions.md)    | Role-based access control, field permissions |
| [Multi-Factor Authentication](./security/mfa.md)   | TOTP configuration and account security      |

### Extensions

| Guide                                          | Description                                   |
| ---------------------------------------------- | --------------------------------------------- |
| [Webhooks](./extensions/webhooks.md)           | Send events to external systems               |
| [Subscriptions](./extensions/subscriptions.md) | Real-time with GraphQL and WebSocket          |
| [Audit & Logging](./extensions/audit.md)       | Action traceability and security events       |
| [Data Export](./extensions/exporting.md)       | Excel/CSV export with safeguards              |
| [Reporting & BI](./extensions/reporting.md)    | Define analytical datasets and visualizations |
| [Background Tasks](./extensions/tasks.md)      | Async mutations and task status tracking      |
| [PDF Generation](./extensions/templating.md)   | HTML templates to PDF                         |
| [Health Monitoring](./extensions/health.md)    | Health endpoints for orchestration            |
| [Schema Metadata](./extensions/metadata.md)    | Schema introspection for dynamic interfaces   |
| [Observability](./extensions/observability.md) | Sentry, OpenTelemetry, and Prometheus metrics |

### GraphQL

| Guide                                       | Description                                     |
| ------------------------------------------- | ----------------------------------------------- |
| [Queries](./graphql/queries.md)             | Lists, filters, pagination, and sorting         |
| [Mutations](./graphql/mutations.md)         | Automatic CRUD, bulk operations, custom methods |
| [Configuration](./graphql/configuration.md) | Complete settings reference                     |

### Performance

| Guide                                           | Description                             |
| ----------------------------------------------- | --------------------------------------- |
| [Optimization](./performance/optimization.md)   | Prefetch, DataLoader, complexity limits |
| [Rate Limiting](./performance/rate-limiting.md) | Request rate limiting                   |

### Deployment

| Guide                                    | Description                                  |
| ---------------------------------------- | -------------------------------------------- |
| [Production](./deployment/production.md) | Docker, checklist, HTTPS, and best practices |

---

## 🚀 Quick Start

```bash
# Installation
pip install rail-django

# Create project
rail-admin startproject my_project
cd my_project

# Initialization
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Access the GraphiQL playground: `http://localhost:8000/graphql/graphiql/`

---

## 🏗️ Project Structure

```
my_project/
├── manage.py           # Django entry point
├── root/               # Main configuration
│   ├── settings/       # Settings (base, dev, prod)
│   ├── urls.py         # Global routing
│   └── asgi.py         # WebSocket support
├── apps/               # Your Django applications
├── requirements/       # Dependencies (base, dev, prod)
└── docs/               # This documentation
```

---

## ⚙️ Main Configuration

All configuration is centralized in `RAIL_DJANGO_GRAPHQL`:

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "authentication_required": True,
        "enable_graphiql": True,
        "auto_camelcase": True,
    },
    "mutation_settings": {
        "generate_create": True,
        "generate_update": True,
        "generate_delete": True,
    },
    "security_settings": {
        "enable_field_permissions": True,
        "enable_rate_limiting": False,
    },
}
```

📖 See [Complete Configuration](./graphql/configuration.md) for all options.

---

## 📊 Key Features

### Auto-Generated Schema

Define your Django models, Rail Django automatically generates:

- GraphQL Types (`DjangoObjectType`)
- Nested Filters (`WhereInput`)
- List/retrieve queries
- Create/update/delete mutations

```python
# apps/store/models.py
class Product(models.Model):
    """
    Product Model.

    Attributes:
        name: Product name.
        price: Unit price.
        is_active: Activation status.
    """
    name = models.CharField("Name", max_length=255)
    price = models.DecimalField("Price", max_digits=10, decimal_places=2)
    is_active = models.BooleanField("Active", default=True)
```

### Automatic GraphQL Query

```graphql
query {
  products(
    where: { isActive: { eq: true }, price: { gt: 50 } }
    orderBy: ["-price"]
  ) {
    id
    name
    price
  }
}
```

### Automatic Mutations

```graphql
mutation {
  createProduct(input: { name: "New", price: 99.99 }) {
    ok
    object {
      id
      name
    }
    errors {
      field
      message
    }
  }
}
```

---

## 🔐 Built-in Security

### JWT Authentication

```graphql
mutation {
  login(username: "user", password: "secret") {
    token
    refreshToken
    user {
      id
      username
    }
  }
}
```

### Field Permissions

```python
class Customer(models.Model):
    email = models.EmailField()

    class GraphQLMeta:
        field_permissions = {
            "email": {
                "roles": ["support", "admin"],
                "visibility": "masked",
                "mask_value": "***@***.com"
            }
        }
```

📖 See [Permissions & RBAC](./security/permissions.md)

---

## 📡 Real-Time Extensions

### Webhooks

Send events to external systems on create/update/delete.

```python
RAIL_DJANGO_WEBHOOKS = {
    "enabled": True,
    "endpoints": [{
        "name": "orders",
        "url": "https://example.com/webhooks/orders",
        "include_models": ["store.Order"],
    }],
}
```

📖 See [Webhooks](./extensions/webhooks.md)

### GraphQL Subscriptions

```graphql
subscription {
  orderCreated(filters: { status: { eq: "pending" } }) {
    event
    node {
      id
      status
    }
  }
}
```

📖 See [Subscriptions](./extensions/subscriptions.md)

---

## 📈 Reporting & Export

### BI Datasets

```python
from rail_django.extensions.reporting import ReportingDataset

ReportingDataset.objects.create(
    code="monthly_sales",
    source_app_label="store",
    source_model="Order",
    dimensions=[{"field": "created_at", "transform": "trunc:month"}],
    metrics=[{"field": "total", "aggregation": "sum", "name": "revenue"}],
)
```

📖 See [Reporting & BI](./extensions/reporting.md)

### Excel/CSV Export

```bash
curl -X POST /api/v1/export/ \
  -H "Authorization: Bearer <jwt>" \
  -d '{"app_name": "store", "model_name": "Product", "file_extension": "xlsx"}'
```

📖 See [Data Export](./extensions/exporting.md)

---

## 🏥 Monitoring

### Health Check

```graphql
query {
  health {
    healthStatus {
      overallStatus
      components {
        databases {
          status
        }
      }
    }
  }
}
```

📖 See [Health Monitoring](./extensions/health.md)

---

## 📚 Additional Resources

- [CHANGELOG](../CHANGELOG.md) - Version history
- [CONTRIBUTING](../CONTRIBUTING.md) - Contribution guide
- [GitHub](https://github.com/raillogistic/rail-django) - Source code

---

**Rail Django** - _Build faster, scale better._
