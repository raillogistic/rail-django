# Table v3 Contract

Implemented GraphQL surface:

- Query `tableBootstrap(app, model, view, objectId)`
- Query `tableRows(input)`
- Mutation `executeTableAction(input)`

The contract is static and backend-driven; frontend no longer needs dynamic list query generation for v3 flow.

