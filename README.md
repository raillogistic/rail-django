# Rail Django

Rail Django is a production-ready GraphQL framework for Django, built on
Graphene-Django. It generates GraphQL contracts from Django models and adds
security, performance, and operations tooling for production APIs.

## Installation

Install from PyPI:

```bash
pip install rail-django
```

## Quickstart

Create and run a new project:

```bash
rail-admin startproject my_api
cd my_api
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://localhost:8000/graphql/` to inspect your API.

## Documentation

The canonical docs live in `rail_django/docs/`. Start from the main index, then
move into the section that matches your workflow.

- [Documentation index](rail_django/docs/index.md)
- [Getting started](rail_django/docs/getting-started/installation.md)
- [Tutorials](rail_django/docs/tutorials/index.md)
- [Core concepts](rail_django/docs/core/models-and-schema.md)
- [Security](rail_django/docs/security/permissions.md)
- [Extensions](rail_django/docs/extensions/index.md)
- [Guides](rail_django/docs/guides/testing.md)
- [Reference](rail_django/docs/reference/api.md)
- [Operations](rail_django/docs/operations/deployment.md)
- [Library internals](rail_django/docs/library/index.md)

## Common references

Use these pages for day-to-day implementation details:

- [CLI reference](rail_django/docs/reference/cli.md)
- [Configuration reference](rail_django/docs/reference/configuration.md)
- [GraphQLMeta reference](rail_django/docs/reference/meta.md)
- [Form contract API](rail_django/docs/reference/form-api.md)
- [Security events reference](rail_django/docs/reference/security-events.md)

## Development

Set up a local editable install, then run unit and integration tests:

```bash
python -m pip install -e .
pytest -m unit
pytest -m integration
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
