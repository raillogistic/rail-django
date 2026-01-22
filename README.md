# Rail Django

Rail Django is a production-ready GraphQL framework for Django, built on top of Graphene-Django. It reduces boilerplate, enforces security best practices, and provides enterprise-grade features out of the box.

## 🚀 Key Features

*   **Auto-Generation**: GraphQL Types, Queries, and Mutations generated from Django Models.
*   **Performance**: Solves N+1 problems automatically with `select_related`/`prefetch_related` injection.
*   **Security**: Built-in RBAC, Query Depth Limiting, and Input Validation.
*   **Developer Experience**: `auto_camelCase` conversion, CLI scaffolding, and clear configuration.
*   **Enterprise Extensions**: Audit Logging, Webhooks, Exporting, and Observability.

## 📚 Documentation

Full documentation is available in the `docs/` directory.

*   [**Getting Started**](docs/getting-started/installation.md)
*   [**Core Concepts**](docs/core/models-and-schema.md)
*   [**Security**](docs/security/authentication.md)
*   [**Extensions**](docs/extensions/index.md)
*   [**Reference**](docs/reference/api.md)

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