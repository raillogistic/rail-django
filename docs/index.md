# Rail Django Documentation

Rail Django is a GraphQL framework built on Django and Graphene. This index
organizes the documentation for API consumers and integrators.

## Supported versions

- Python 3.11+
- Django 4.2+
- Graphene 3.3+
- graphene-django 3.1.5+

## Getting started

- [Quick start](getting-started/quickstart.md)
- [CLI and management commands](getting-started/cli.md)
- [Migration notes](getting-started/migration.md)

## Guides

- [GraphQL API](guides/graphql.md)
- [REST API and health endpoints](guides/rest-api.md)
- [Subscriptions](guides/subscriptions.md)
- [Webhooks](guides/webhooks.md)
- [Reporting and BI](guides/reporting.md)

## Extensions

- [Extensions index](extensions/index.md)

## Reference

- [Configuration](reference/configuration.md)
- [GraphQLMeta](reference/meta.md)
- [Security](reference/security.md)

## Operations

- [Operations index](operations/index.md)

## Contributing

- [Architecture](contributing/architecture.md)
- [Modules](contributing/modules.md)
- [Testing](contributing/testing.md)

## Conventions

- Default GraphQL field names are snake_case (`auto_camelcase = False`).
- If you enable `auto_camelcase`, field names are exposed in camelCase.
- Multi-schema endpoints live at `/graphql/<schema_name>/`.
