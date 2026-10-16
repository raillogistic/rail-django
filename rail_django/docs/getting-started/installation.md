# Installation guide

This guide covers the requirements and steps to install Rail Django and set up your development environment.

## Prerequisites

- **Python**: 3.11 or higher
- **Django**: 5.2.18 or higher (5.2 LTS is tested)
- **Graphene**: resolved by graphene-django; scaffold uses 3.4.1 or higher
- **Database**: PostgreSQL (recommended), MySQL, or SQLite (for development)
- **Redis** (optional): Highly recommended for caching, rate limiting, and subscriptions.

## Package Installation

You can install `rail-django` directly from PyPI:

```bash
pip install rail-django
```

### Optional Dependencies
The subscriptions extra is available. Application integrations in scaffold requirements are separate from the library runtime dependencies:

```bash
# For GraphQL Subscriptions
pip install rail-django[subscriptions]

# For PDF generation, install the renderer separately
pip install weasyprint
```

## Creating a New Project

Rail Django includes a CLI tool `rail-admin` to scaffold a new project with the recommended directory structure and optimal defaults.

```bash
# 1. Start a new project
rail-admin startproject my_api
cd my_api

# 2. Apply initial migrations
python manage.py migrate

# 3. Create an administrator
python manage.py createsuperuser

# 4. Start the development server
python manage.py runserver
```

## Recommended Project Structure

When using `rail-admin`, your project is organized as follows:

```text
my_api/
├── manage.py           # Django entry point
├── root/               # Project configuration
│   ├── settings/       # Settings split by environment
│   ├── urls.py         # Main URL routing
│   └── asgi.py         # ASGI config for WebSockets
├── apps/               # Your Django applications
├── requirements/       # Dependency lists
└── deploy/             # Docker and CI/CD configuration
```

## Verifying Installation

Access the interactive GraphQL IDE (GraphiQL) at:
`http://localhost:8000/graphql/`

Execute a simple test query:
```graphql
query {
  __schema {
    queryType { name }
  }
}
```

## Next Steps

- Follow the [Quickstart Guide](./quickstart.md) to build your first API.
- Learn about [Complete Configuration](../core/configuration.md).
- Explore [Models & Schema](../core/models-and-schema.md).
