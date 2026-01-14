# Rail Django

Rail Django is a GraphQL framework for Django built on top of Graphene-Django.
It reduces boilerplate and enforces secure, production-ready defaults.

## Quick links
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Usage](#usage)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Key features
- Automatic GraphQL type, query, and mutation generation from Django models.
- Built-in security: RBAC, query depth limits, and input validation.
- Performance defaults: select_related and prefetch_related injection to avoid N+1.
- Extensions for health checks, audit logs, and export utilities.

## Installation
Install from the official GitHub repository:

```bash
python -m pip install "rail-django @ git+https://github.com/raillogistic/rail-django.git"
```

## Quickstart
Use the CLI to scaffold a project:

```bash
rail-admin startproject my_api
cd my_api
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open GraphiQL at `http://localhost:8000/graphql`.

## Usage
See the [quickstart](docs/getting-started/quickstart.md) for the basic workflow, and the [GraphQL guide](docs/guides/graphql.md) for how to define types, queries, and mutations.

## Supported versions
- Python 3.8+
- Django 4.2+
- Graphene 3.3+
- graphene-django 3.1.5+

## Documentation
Start at [docs/index.md](docs/index.md) for the full table of contents.

Getting started
- [Quickstart](docs/getting-started/quickstart.md)
- [CLI](docs/getting-started/cli.md)
- [Migration](docs/getting-started/migration.md)

Guides
- [Guides index](docs/guides/index.md)
- [GraphQL](docs/guides/graphql.md)

Reference
- [Configuration](docs/reference/configuration.md)
- [Security](docs/reference/security.md)

Internals and testing
- [Architecture](docs/contributing/architecture.md)
- [Modules](docs/contributing/modules.md)
- [Testing](docs/contributing/testing.md)

Extensions and operations
- [Extensions](docs/extensions/index.md)
- [Operations](docs/operations/index.md)

## Contributing
Contributions are welcome. Please read the contributor docs before opening a pull request.

## License
MIT
