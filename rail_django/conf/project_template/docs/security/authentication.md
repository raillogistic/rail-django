# JWT Authentication

## Overview

Rail Django integrates a complete JWT (JSON Web Token) authentication system to secure your GraphQL APIs. This guide covers configuration, authentication mutations, and best practices.

---

## Table of Contents

1. [Configuration](#configuration)
2. [Authentication Mutations](#authentication-mutations)
3. [Using Tokens](#using-tokens)
4. [Cookie Authentication](#cookie-authentication)
5. [Environment Variables](#environment-variables)
6. [Best Practices](#best-practices)

---

## Configuration

### Main Settings

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        # Requires a valid JWT for all requests
        "authentication_required": True,
        # Disables login/register mutations if False
        "disable_security_mutations": False,
    },
    "security_settings": {
        # Enables authentication checks
        "enable_authentication": True,
        # Session timeout in minutes
        "session_timeout_minutes": 30,
    },
}
```

### JWT Configuration

```python
# Token lifetime
JWT_ACCESS_TOKEN_LIFETIME = timedelta(minutes=30)
JWT_REFRESH_TOKEN_LIFETIME = timedelta(days=7)

# Signing algorithm
JWT_ALGORITHM = "HS256"

# Cookie authentication (optional)
JWT_ALLOW_COOKIE_AUTH = False
JWT_ENFORCE_CSRF = True
JWT_COOKIE_NAME = "access_token"
JWT_COOKIE_SECURE = True  # HTTPS only
JWT_COOKIE_HTTPONLY = True
JWT_COOKIE_SAMESITE = "Lax"
```

---

## Authentication Mutations

### Login

Authenticates a user and returns access tokens.

```graphql
mutation Login($username: String!, $password: String!) {
  login(username: $username, password: $password) {
    ok
    token # JWT access token
    refreshToken # Refresh token
    expiresAt # Token expiration date
    errors # List of any errors
    user {
      id
      username
      email
      isStaff
    }
  }
}
```

**Variables:**

```json
{
  "username": "john.doe",
  "password": "my_secret_password"
}
```

**Success Response:**

```json
{
  "data": {
    "login": {
      "ok": true,
      "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "expiresAt": "2026-01-16T12:30:00Z",
      "errors": null,
      "user": {
        "id": "1",
        "username": "john.doe",
        "email": "john@example.com",
        "isStaff": false
      }
    }
  }
}
```

**Error Response:**

```json
{
  "data": {
    "login": {
      "ok": false,
      "token": null,
      "errors": ["Invalid credentials"]
    }
  }
}
```

### Token Refresh

Obtains a new access token from the refresh token.

```graphql
mutation RefreshToken($refreshToken: String!) {
  refreshToken(refreshToken: $refreshToken) {
    ok
    token # New access token
    refreshToken # New refresh token (optional rotation)
    expiresAt
    errors
  }
}
```

**Variables:**

```json
{
  "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Logout

Invalidates the current token (if blacklist is enabled).

```graphql
mutation Logout {
  logout {
    ok
  }
}
```

### Register

Creates a new user account.

```graphql
mutation Register($input: RegisterInput!) {
  register(input: $input) {
    ok
    token
    user {
      id
      username
      email
    }
    errors
  }
}
```

**Variables:**

```json
{
  "input": {
    "username": "new_user",
    "email": "new@example.com",
    "password": "Password123!",
    "passwordConfirm": "Password123!"
  }
}
```

### Current User (Me)

Retrieves information about the authenticated user.

```graphql
query Me {
  me {
    id
    username
    email
    firstName
    lastName
    isStaff
    isSuperuser
    permissions # List of Django permissions
    groups {
      id
      name
    }
  }
}
```

---

## Using Tokens

### Authorization Header

Add the JWT token to the `Authorization` header of each request:

```http
POST /graphql/gql/ HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json

{
  "query": "{ me { id username } }"
}
```

### JavaScript Example (Fetch)

```javascript
const token = localStorage.getItem("access_token");

const response = await fetch("/graphql/gql/", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  },
  body: JSON.stringify({
    query: `
      query {
        me { id username }
      }
    `,
  }),
});

const data = await response.json();
```

### Apollo Client Example

```typescript
import { ApolloClient, InMemoryCache, HttpLink } from "@apollo/client";
import { setContext } from "@apollo/client/link/context";

const httpLink = new HttpLink({ uri: "/graphql/gql/" });

const authLink = setContext((_, { headers }) => {
  const token = localStorage.getItem("access_token");
  return {
    headers: {
      ...headers,
      authorization: token ? `Bearer ${token}` : "",
    },
  };
});

export const client = new ApolloClient({
  link: authLink.concat(httpLink),
  cache: new InMemoryCache(),
});
```

### Expiration Handling

Implement an interceptor to automatically refresh expired tokens:

```typescript
import { onError } from "@apollo/client/link/error";

const errorLink = onError(({ graphQLErrors, operation, forward }) => {
  if (graphQLErrors) {
    for (const err of graphQLErrors) {
      if (err.message.includes("Signature has expired")) {
        // Refresh the token
        const refreshToken = localStorage.getItem("refresh_token");
        // ... call refreshToken mutation
        // ... update stored token
        // ... retry original request
        return forward(operation);
      }
    }
  }
});
```

---

## Cookie Authentication

For web applications, you can use HTTP-only cookies instead of Authorization headers.

### Activation

```python
# settings.py
JWT_ALLOW_COOKIE_AUTH = True
JWT_ENFORCE_CSRF = True  # Recommended for cookies
JWT_COOKIE_NAME = "access_token"
JWT_COOKIE_SECURE = True  # HTTPS only
JWT_COOKIE_HTTPONLY = True  # Inaccessible via JavaScript
JWT_COOKIE_SAMESITE = "Lax"  # Basic CSRF protection
```

### How It Works

1. The `login` mutation sets the cookie automatically.
2. The browser sends the cookie with each request.
3. CSRF protection applies to mutations.

### CSRF Protection

When `JWT_ENFORCE_CSRF=True`, include the CSRF token in mutation requests:

```javascript
// Read CSRF token from Django cookie
function getCsrfToken() {
  return document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="))
    ?.split("=")[1];
}

const response = await fetch("/graphql/gql/", {
  method: "POST",
  credentials: "include", // Sends cookies
  headers: {
    "Content-Type": "application/json",
    "X-CSRFToken": getCsrfToken(),
  },
  body: JSON.stringify({ query: "mutation { ... }" }),
});
```

---

## Environment Variables

| Variable                     | Description                   | Default             |
| ---------------------------- | ----------------------------- | ------------------- |
| `JWT_SECRET_KEY`             | Secret key for signing tokens | `DJANGO_SECRET_KEY` |
| `JWT_ACCESS_TOKEN_LIFETIME`  | Access token lifetime         | `30 minutes`        |
| `JWT_REFRESH_TOKEN_LIFETIME` | Refresh token lifetime        | `7 days`            |
| `JWT_ALLOW_COOKIE_AUTH`      | Enables cookie authentication | `False`             |
| `JWT_ENFORCE_CSRF`           | Enforces CSRF for cookies     | `True`              |

---

## Best Practices

### 1. Token Security

```python
# ✅ Use a strong and unique secret key
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

# ✅ Short lifetime for access tokens
JWT_ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)

# ✅ Refresh token rotation
JWT_ROTATE_REFRESH_TOKENS = True
JWT_BLACKLIST_AFTER_ROTATION = True
```

### 2. Client-Side Storage

```javascript
// ✅ For SPA applications: LocalStorage with refresh token flow
localStorage.setItem("access_token", token);

// ✅ For classic web applications: HTTP-only cookies
// (handled automatically by the server)

// ❌ Avoid storing sensitive tokens in SessionStorage
// ❌ Never expose the refresh token in the URL
```

### 3. Error Handling

Handle authentication errors consistently:

```python
# Returned errors include:
# - "Invalid credentials"
# - "Signature has expired"
# - "Token is invalid"
# - "User account is disabled"
```

### 4. Audit

Enable authentication event logging:

```python
RAIL_DJANGO_GRAPHQL = {
    "middleware_settings": {
        "log_queries": True,
        "log_mutations": True,
    }
}
```

📖 See [Audit & Logging](../extensions/audit.md) for more details.

---

## Troubleshooting

### Error: "Signature has expired"

**Cause:** The JWT token has expired.

**Solution:** Use the `refreshToken` mutation to obtain a new access token.

### Error: "Token is invalid"

**Cause:** Malformed token, modified, or different secret key.

**Solution:**

1. Verify that `JWT_SECRET_KEY` is consistent across environments.
2. Ask the user to log in again.

### Error: "Authentication required"

**Cause:** Request without token to a protected endpoint.

**Solution:** Add the `Authorization: Bearer <token>` header.

---

## See Also

- [Permissions & RBAC](./permissions.md)
- [Multi-Factor Authentication](./mfa.md)
- [Audit & Logging](../extensions/audit.md)
