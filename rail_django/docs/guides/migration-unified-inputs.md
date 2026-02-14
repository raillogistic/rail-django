# Migration Guide: Unified Relation Inputs

Rail Django has moved from the "Dual Field" pattern (for example, `author` + `nested_author`) to "Unified Relation Inputs" (Prisma-style). This guide explains how to migrate your client applications.

## What Changed?

Previously, you had separate fields for ID linking and nested creation:

**Old (Deprecated):**
```graphql
mutation {
  createPost(input: {
    title: "Hello",
    author: "1",                    # Link ID
    nestedTags: [{ name: "News" }]  # Nested Create
  }) { ... }
}
```

Now, there is a **single** field for each relationship, accepting an object with operation keys (`connect`, `create`, `update`, `disconnect`, `set`).

**New (Unified):**
```graphql
mutation {
  createPost(input: {
    title: "Hello",
    author: { connect: "1" },
    tags: {
      create: [{ name: "News" }]
    }
  }) { ... }
}
```

## Migration Steps

### 1. Foreign Keys (One-to-Many)

Replace direct ID assignment with `{ connect: ID }`.

**Before:**
```javascript
variables = {
  input: {
    author: "123"
  }
}
```

**After:**
```javascript
variables = {
  input: {
    author: { connect: "123" }
  }
}
```

Replace `nested_Field` with `{ create: ... }` inside the main field.

**Before:**
```javascript
variables = {
  input: {
    nestedAuthor: { name: "John" }
  }
}
```

**After:**
```javascript
variables = {
  input: {
    author: { create: { name: "John" } }
  }
}
```

### 2. Many-to-Many & Reverse Relations

The input is no longer a list of objects or a JSON string. It is an object containing list operations.

**Before:**
```javascript
variables = {
  input: {
    tags: ["1", "2"], // IDs
    nestedTags: [{ name: "New" }]
  }
}
```

**After:**
```javascript
variables = {
  input: {
    tags: {
      connect: ["1", "2"],
      create: [{ name: "New" }]
    }
  }
}
```

### 3. Updates

Use `disconnect` to remove items from a list, or `set` to replace the entire list.

**Example:**
```javascript
variables = {
  input: {
    tags: {
      disconnect: ["3"],
      connect: ["4"]
    }
  }
}
```

## Type Changes

Introspection will show new types like `PostCategoryRelationInput` instead of `ID` or `PostNestedInput`.

- `connect`: Accepts ID or List of IDs.
- `create`: Accepts Input Object or List of Input Objects.
- `update`: Accepts Input Object (with ID) or List.
- `disconnect`: (List only) Accepts List of IDs.
- `set`: (List only) Accepts List of IDs.
