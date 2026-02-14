# Rail Django documentation

Rail Django is a production-ready GraphQL framework for Django. This
documentation helps you move from installation to production operations, with
clear references for schema generation, security, and extensions.

Rail Django builds on
[Graphene-Django](https://docs.graphene-python.org/projects/django/en/latest/)
and adds automatic schema generation, policy-driven security, and operational
tooling for larger deployments.

## Start here

If you are new to Rail Django, begin with setup and your first API build.

- [Installation](getting-started/installation.md)
- [Quickstart tutorial](getting-started/quickstart.md)
- [Architecture](getting-started/architecture.md)

## Learn by tutorial

Use the tutorials to implement real features end to end.

- [Build your first API](tutorials/first-api.md)
- [Authentication tutorial](tutorials/authentication.md)
- [Permissions walkthrough](tutorials/permissions.md)
- [Queries tutorial](tutorials/queries.md)
- [Mutations tutorial](tutorials/mutations.md)
- [Configuration tutorial](tutorials/configuration.md)

## Core concepts

These pages explain the default behavior and key framework contracts.

- [Models and schema](core/models-and-schema.md)
- [Queries](core/queries.md)
- [Filtering](core/filtering.md)
- [Mutations](core/mutations.md)
- [Configuration](core/configuration.md)
- [Performance](core/performance.md)

## Security

Use this section to configure authentication, authorization, and validation.

- [Authentication](security/authentication.md)
- [Permissions](security/permissions.md)
- [Validation](security/validation.md)

## Extensions and guides

Use optional modules and implementation guides to fit your architecture.

- [Extensions overview](extensions/index.md)
- [Data importing](extensions/importing.md)
- [Testing guide](guides/testing.md)
- [Plugin guide](guides/plugins.md)
- [Migration to unified relation inputs](guides/migration-unified-inputs.md)
- [Troubleshooting](guides/troubleshooting.md)

## Reference and operations

Use these references for day-to-day implementation and production maintenance.

- [Deployment](operations/deployment.md)
- [API reference](reference/api.md)
- [CLI reference](reference/cli.md)
- [GraphQLMeta reference](reference/meta.md)
- [Security reference](reference/security.md)

## Next steps

After you complete quickstart, move to
[mutations](core/mutations.md) and [permissions](security/permissions.md) to
define your production data and access model.
