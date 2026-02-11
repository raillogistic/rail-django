# Architecture

Rail Django is designed to sit between Django models and the Graphene execution layer, automating the tedious parts of schema creation while injecting performance and security best practices.

## Core Components

### 1. Schema Registry
The `SchemaRegistry` (`rail_django.core.registry`) is the central brain. It:
*   Scans installed apps for `schema.py` or `graphql_schema.py`.
*   Maintains a registry of all active schemas (supporting multi-schema setups).
*   Manages "Schema Builders".

### 2. Schema Builder & Generators
For each registered schema, a `SchemaBuilder` (`rail_django.core.schema`) orchestrates the creation of the GraphQL schema. It delegates to specialized generators:
*   **TypeGenerator**: Converts Django Models -> Graphene Types. It handles field naming (snake_case -> camelCase) and type mapping.
*   **QueryGenerator**: Creates standard queries (`<model>`, `<model>List`, `<model>Page`, `<model>Group`) with built-in filtering and pagination.
*   **MutationGenerator**: Creates standard mutations (`create<Model>`, `update<Model>`, `delete<Model>`).

### 3. Middleware Pipeline
Rail Django injects a robust middleware stack:
*   **Auth Middleware**: Integreates with Django authentication.
*   **Performance Middleware**: Auto-detects N+1 opportunities and optimizes them.
*   **Security Middleware**: Enforces rate limiting and query depth analysis.

### 4. GraphQLMeta
The `GraphQLMeta` inner class on your models (or in a separate configuration) acts as the configuration DSL. It tells the generators:
*   Which fields to expose/exclude.
*   What permissions are required (`login_required`, `permission_classes`).
*   Which filters to enable.

## Request Lifecycle

1.  **Request**: Client sends a POST request to `/graphql`.
2.  **Routing**: `MultiSchemaGraphQLView` determines which schema to use (default is `default`).
3.  **Authentication**: Middleware verifies the user.
4.  **Parsing & Validation**: Query is parsed; depth and complexity are checked.
5.  **Execution**:
    *   Resolvers fetch data.
    *   `select_related`/`prefetch_related` are applied automatically based on the requested fields.
    *   Field-level permissions are checked.
6.  **Response**: JSON result is returned.

## Design Philosophy

*   **Convention over Configuration**: Things should "just work" with standard Django models.
*   **Secure by Default**: You have to opt-out of security, not opt-in.
*   **Production First**: Performance and logging are first-class citizens, not afterthoughts.
