# Authentication and MFA

Rail Django ships JWT-based authentication, cookie support, and MFA helpers.
This page documents the auth contracts that exist in the current extension
implementation.

## Authentication architecture

GraphQL auth is provided by `rail_django.extensions.auth` and MFA flows are
provided by `rail_django.extensions.mfa`.

Core auth mutations exposed by `AuthMutations`:

- `login`
- `verifyMfaLogin`
- `refreshToken`
- `revokeSession`
- `revokeAllSessions`
- `logout`

Core auth queries:

- `me`
- `viewer`

## Enable authentication

Use schema and security settings, then include Django authentication middleware.

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "authentication_required": True,
    },
    "security_settings": {
        "enable_authentication": True,
    },
}

MIDDLEWARE = [
    # ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "rail_django.middleware.auth.GraphQLAuthenticationMiddleware",
]
```

## Login and token refresh

Example login mutation:

```graphql
mutation Login($username: String!, $password: String!) {
  login(username: $username, password: $password) {
    ok
    token
    refreshToken
    mfaRequired
    mfaSetupRequired
    ephemeralToken
    errors
  }
}
```

Example refresh mutation:

```graphql
mutation Refresh($refreshToken: String) {
  refreshToken(refreshToken: $refreshToken) {
    ok
    token
    refreshToken
    expiresAt
    errors
  }
}
```

## JWT settings

The auth extension reads these settings directly:

```python
JWT_SECRET_KEY = "<secret>"  # defaults to Django SECRET_KEY
JWT_ACCESS_TOKEN_LIFETIME = 3600
JWT_REFRESH_TOKEN_LIFETIME = 86400
JWT_ROTATE_REFRESH_TOKENS = True
JWT_REFRESH_REUSE_DETECTION = True
JWT_REFRESH_TOKEN_CACHE = "default"

JWT_AUTH_COOKIE = "jwt"
JWT_REFRESH_COOKIE = "refresh_token"
JWT_COOKIE_SECURE = True
JWT_COOKIE_SAMESITE = "Lax"
```

## MFA login flow

When MFA is required for a user, `login` returns `mfaRequired: true` and an
`ephemeralToken`. Complete login with:

```graphql
mutation VerifyMfa($code: String!, $ephemeralToken: String!) {
  verifyMfaLogin(code: $code, ephemeralToken: $ephemeralToken) {
    ok
    token
    refreshToken
    errors
  }
}
```

MFA policy and behavior are controlled by `MFA_*` settings, including:

- `MFA_ENABLED`
- `MFA_REQUIRED_FOR_ALL_USERS`
- `MFA_REQUIRED_FOR_STAFF`
- `MFA_TOTP_VALIDITY_WINDOW`
- `MFA_BACKUP_CODES_COUNT`

## Session revocation

Use `revokeSession(sessionId: String!)` to revoke a refresh-token family, or
`revokeAllSessions` to revoke the current session context.

## Current user query

Use `me` (or `viewer`) to fetch authenticated user data plus permissions and
roles resolved by the extension.

```graphql
query Me {
  me {
    id
    username
    permissions
    roles { name }
  }
}
```

## Next steps

Continue with [permissions](./permissions.md) and
[audit logging](../extensions/audit-logging.md).
