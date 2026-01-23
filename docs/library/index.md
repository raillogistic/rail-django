# Rail Django Library Reference

This section provides detailed documentation for every module in the Rail Django library. Use this reference when you need to understand how the framework works internally, extend its functionality, or contribute to its development.

## Library Structure Overview

```
rail_django/
├── core/                 # Core Framework Logic
│   ├── config/           # Configuration loading and helpers
│   ├── meta/             # GraphQLMeta processing
│   ├── middleware/       # Graphene middleware stack
│   ├── registry/         # Schema registry system
│   ├── scalars/          # Custom GraphQL scalars
│   ├── schema/           # SchemaBuilder implementation
│   └── settings/         # Settings dataclasses
├── generators/           # Auto-Generation Engine
│   ├── filters/          # FilterSet generation
│   ├── introspector/     # Model introspection
│   ├── mutations/        # CRUD mutation generation
│   ├── nested/           # Nested operation handling
│   ├── pipeline/         # Mutation pipeline system
│   ├── queries/          # Query generation
│   ├── subscriptions/    # Subscription generation
│   └── types/            # Type generation
├── security/             # Security Engine
│   ├── audit/            # Audit logging
│   ├── field_permissions/# Field-level permissions
│   ├── graphql/          # GraphQL security rules
│   ├── rbac/             # Role-Based Access Control
│   └── validation/       # Input validation
├── extensions/           # Pluggable Feature Modules
│   ├── auth/             # JWT authentication
│   ├── excel/            # Excel builder
│   ├── exporting/        # Data export engine
│   ├── health/           # Health checks
│   ├── metadata/         # Metadata introspection V2
│   ├── reporting/        # BI reporting engine
│   ├── subscriptions/    # WebSocket subscriptions
│   ├── tasks/            # Background task system
│   ├── templating/       # PDF generation
│   └── multitenancy/     # Tenant isolation
├── plugins/              # Plugin System
├── webhooks/             # Webhook dispatching
├── api/                  # REST API endpoints
├── bin/                  # CLI tools
├── conf/                 # Templates and settings
├── views/                # GraphQL views
└── testing/              # Test utilities
```

## Module Documentation

### Core Modules

| Module | Description | Documentation |
|--------|-------------|---------------|
| [Schema Builder](./core/schema-builder.md) | Builds GraphQL schema from Django models | Architecture, API |
| [Schema Registry](./core/schema-registry.md) | Manages multiple schema instances | Multi-schema support |
| [Settings System](./core/settings.md) | Hierarchical configuration | All settings explained |
| [GraphQLMeta](./core/graphql-meta.md) | Per-model configuration | Complete reference |
| [Middleware Stack](./core/middleware.md) | Request processing pipeline | Extension points |
| [Custom Scalars](./core/scalars.md) | Extended GraphQL types | DateTime, JSON, etc. |

### Generator Modules

| Module | Description | Documentation |
|--------|-------------|---------------|
| [Type Generator](./generators/type-generator.md) | Creates GraphQL types | Object types, inputs, enums |
| [Query Generator](./generators/query-generator.md) | Creates query fields | List, single, paginated |
| [Mutation Generator](./generators/mutation-generator.md) | Creates mutation fields | CRUD, bulk, methods |
| [Filter Generator](./generators/filter-generator.md) | Creates filter inputs | Operators, relations |
| [Subscription Generator](./generators/subscription-generator.md) | Creates subscriptions | Real-time events |
| [Model Introspector](./generators/introspector.md) | Analyzes Django models | Field analysis |
| [Pipeline System](./generators/pipeline.md) | Mutation execution flow | Steps, factories |

### Security Modules

| Module | Description | Documentation |
|--------|-------------|---------------|
| [RBAC System](./security/rbac.md) | Role-based access control | Roles, permissions |
| [Field Permissions](./security/field-permissions.md) | Field-level security | Masking, visibility |
| [Input Validation](./security/validation.md) | Input sanitization | XSS, SQL injection |
| [Audit System](./security/audit.md) | Security event logging | Events, reports |
| [Policy Engine](./security/policies.md) | Allow/deny rules | Priority-based |
| [GraphQL Security](./security/graphql-security.md) | Query analysis | Depth, complexity |

### Extension Modules

| Module | Description | Documentation |
|--------|-------------|---------------|
| [Authentication](./extensions/auth.md) | JWT authentication | Login, tokens, MFA |
| [Data Export](./extensions/exporting.md) | Excel/CSV export | Async jobs, security |
| [Templating](./extensions/templating.md) | PDF generation | Templates, rendering |
| [Health Checks](./extensions/health.md) | System monitoring | Components, metrics |
| [Metadata V2](./extensions/metadata.md) | Schema introspection | Frontend integration |
| [Reporting](./extensions/reporting.md) | BI dashboards | Datasets, aggregations |
| [Subscriptions](./extensions/subscriptions.md) | Real-time events | WebSocket, channels |
| [Tasks](./extensions/tasks.md) | Background jobs | Backends, tracking |
| [Multitenancy](./extensions/multitenancy.md) | Tenant isolation | Row-level, schema |
| [Webhooks](./extensions/webhooks.md) | Event dispatching | Endpoints, auth |

### Utility Modules

| Module | Description | Documentation |
|--------|-------------|---------------|
| [Plugin System](./plugins/index.md) | Extension hooks | Lifecycle, registration |
| [REST API](./api/index.md) | REST endpoints | Schema management |
| [CLI Tools](./cli/index.md) | Command-line tools | rail-admin, commands |
| [Testing Utilities](./testing/index.md) | Test helpers | Clients, fixtures |

## Quick Navigation

- **I want to understand how schema generation works** → [Schema Builder](./core/schema-builder.md)
- **I want to customize field exposure** → [GraphQLMeta](./core/graphql-meta.md)
- **I want to add custom security rules** → [RBAC System](./security/rbac.md)
- **I want to export data** → [Data Export](./extensions/exporting.md)
- **I want to add real-time features** → [Subscriptions](./extensions/subscriptions.md)
- **I want to generate PDFs** → [Templating](./extensions/templating.md)
- **I want to extend the framework** → [Plugin System](./plugins/index.md)
