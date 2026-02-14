# Rail Django library internals

This section documents internal architecture for contributors and advanced
integrators. Use these pages to understand schema generation, module
boundaries, and extension points inside Rail Django.

## Core internals

These modules define schema discovery, build orchestration, and model-level
metadata behavior.

- [Schema builder internals](./core/schema-builder.md)
- [Schema registry](./core/schema-registry.md)
- [GraphQLMeta reference](./core/graphql-meta.md)

## Generator internals

These modules build generated GraphQL contracts from Django models.

- [Type generator internals](./generators/type-generator.md)
- [Query generator](./generators/query-generator.md)
- [Mutation generator internals](./generators/mutation-generator.md)

## Security internals

These pages describe role resolution, policy evaluation, and access checks.

- [Security module API](./security/index.md)
- [RBAC internals](./security/rbac.md)

## Extension internals

Use this section to understand how optional modules attach into the framework.

- [Extensions module API](./extensions/index.md)

## Next steps

If you are extending internal behavior, pair this section with the
[plugins guide](../guides/plugins.md) and
[testing guide](../guides/testing.md).
