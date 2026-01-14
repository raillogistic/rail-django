# Rail Django

Rail Django is a GraphQL framework for Django built on top of Graphene-Django.
It reduces boilerplate and enforces secure, production-ready defaults.

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

## Supported versions
- Python 3.8+
- Django 4.2+
- Graphene 3.3+
- graphene-django 3.1.5+

## Project docs
See the docs in `docs/`:
- `docs/architecture.md`
- `docs/modules.md`
- `docs/security.md`
- `docs/testing.md`

## Contributing
Contributions are welcome. Please read the contributor docs before opening a pull request.

License: MIT
