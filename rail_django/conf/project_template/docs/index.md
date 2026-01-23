# Rail Django Documentation

Welcome to the **Rail Django Documentation**! This comprehensive guide will teach you everything you need to build, secure, and deploy production-ready GraphQL APIs with Django.

---

## Quick Links

| Getting Started | Core Features | Extensions |
|-----------------|---------------|------------|
| [Quick Start](./getting-started/quickstart.md) | [Queries](./graphql/queries.md) | [Subscriptions](./extensions/subscriptions.md) |
| [Installation](./getting-started/installation.md) | [Mutations](./graphql/mutations.md) | [Webhooks](./extensions/webhooks.md) |
| [Configuration](./graphql/configuration.md) | [Authentication](./security/authentication.md) | [Data Export](./extensions/exporting.md) |
| | [Permissions](./security/permissions.md) | [PDF Templates](./extensions/templating.md) |

---

## Documentation Index

### Getting Started
- [**Quick Start**](./getting-started/quickstart.md) - Create your first API in 10 minutes
- [**Installation**](./getting-started/installation.md) - Complete setup instructions

### Tutorials
- [**Building Your First API**](./tutorials/first-api.md) - Complete beginner tutorial
- [**Queries Deep Dive**](./tutorials/queries.md) - Filtering, pagination, ordering
- [**Mutations Deep Dive**](./tutorials/mutations.md) - CRUD and nested operations
- [**Authentication**](./tutorials/authentication.md) - JWT and session auth
- [**Permissions**](./tutorials/permissions.md) - RBAC and access control
- [**Configuration Reference**](./tutorials/configuration.md) - All settings explained

### GraphQL Reference
- [**Queries**](./graphql/queries.md) - Query syntax and filtering
- [**Mutations**](./graphql/mutations.md) - CRUD operations
- [**Configuration**](./graphql/configuration.md) - Schema settings

### Security
- [**Authentication**](./security/authentication.md) - JWT tokens and login
- [**Permissions**](./security/permissions.md) - Role-based access control
- [**MFA**](./security/mfa.md) - Multi-factor authentication

### Extensions
- [**Subscriptions**](./extensions/subscriptions.md) - Real-time WebSocket events
- [**Webhooks**](./extensions/webhooks.md) - Event notifications
- [**Data Export**](./extensions/exporting.md) - Excel and CSV export
- [**PDF Templates**](./extensions/templating.md) - Document generation
- [**Audit Logging**](./extensions/audit.md) - Track all changes
- [**Health Checks**](./extensions/health.md) - System monitoring
- [**Background Tasks**](./extensions/tasks.md) - Async processing
- [**Reporting**](./extensions/reporting.md) - BI and analytics
- [**Metadata API**](./extensions/metadata.md) - Schema introspection

### Performance
- [**Query Optimization**](./performance/optimization.md) - N+1 prevention
- [**Rate Limiting**](./performance/rate-limiting.md) - Request throttling

### Deployment
- [**Production Guide**](./deployment/production.md) - Docker and manual deployment

### Full Usage Guide
- [**Complete Usage Guide**](./usage.md) - Everything in one document

---

## Learning Paths

### Path 1: Complete Beginner
New to GraphQL or Django? Start here:
1. [Quick Start](./getting-started/quickstart.md)
2. [Building Your First API](./tutorials/first-api.md)
3. [Queries Deep Dive](./tutorials/queries.md)
4. [Mutations Deep Dive](./tutorials/mutations.md)

### Path 2: Add Security
Secure your API:
1. [Authentication](./tutorials/authentication.md)
2. [Permissions](./tutorials/permissions.md)
3. [Audit Logging](./extensions/audit.md)

### Path 3: Real-Time Features
Add live updates:
1. [Subscriptions](./extensions/subscriptions.md)
2. [Webhooks](./extensions/webhooks.md)

### Path 4: Production Ready
Deploy your API:
1. [Configuration](./tutorials/configuration.md)
2. [Performance](./performance/optimization.md)
3. [Production Deployment](./deployment/production.md)

---

## Quick Reference

### Start Development Server
```bash
python manage.py runserver
```

### Access GraphQL Playground
Open http://localhost:8000/graphql/ in your browser.

### Common Commands
```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run tests
python manage.py test
```

### Example Query
```graphql
query {
  products(
    where: { status: { eq: "active" } }
    orderBy: ["-price"]
    limit: 10
  ) {
    id
    name
    price
    category { name }
  }
}
```

### Example Mutation
```graphql
mutation {
  createProduct(input: {
    name: "New Product"
    price: 99.99
    categoryId: "1"
  }) {
    ok
    product { id name }
    errors { field message }
  }
}
```

---

## Getting Help

- **Full Guide**: See [Complete Usage Guide](./usage.md)
- **Examples**: Check the `apps/store/` directory
- **Issues**: Report bugs on GitHub

---

Next: [Quick Start →](./getting-started/quickstart.md)
