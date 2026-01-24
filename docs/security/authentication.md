# Authentication & MFA

Rail Django provides a comprehensive security layer on top of Django's native authentication, including full JWT support and Multi-Factor Authentication (MFA).

## Overview

The authentication system features:
- **JWT (JSON Web Token)**: Built-in mutations for login, refresh, and logout.
- **Session Support**: Compatibility with standard Django session-based auth.
- **MFA (Multi-Factor Authentication)**: TOTP-based second factor (Google Authenticator, etc.).
- **Middleware**: Automatic user population in GraphQL context.
- **Secure by Default**: Protection against common vulnerabilities (CSRF, Brute force).

## Configuration

Enable authentication in your settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "authentication_required": True,
    },
    "security_settings": {
        "enable_authentication": True,
    },
}

# Middleware setup
MIDDLEWARE = [
    # ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "rail_django.middleware.auth.GraphQLAuthenticationMiddleware",
    # ...
]
```

## JWT Authentication

Rail Django uses JWT for stateless authentication, ideal for mobile and modern web apps.

### Authentication Mutations

#### 1. Login
Authenticates credentials and returns tokens.

```graphql
mutation Login($username: String!, $password: String!) {
  login(username: $username, password: $password) {
    ok
    token # Access Token
    refreshToken
    user { username }
  }
}
```

#### 2. Token Refresh
Use the refresh token to obtain a new access token when it expires.

```graphql
mutation Refresh($token: String!) {
  refreshToken(refreshToken: $token) {
    token
    expiresAt
  }
}
```

### Using the Token
Include the token in the `Authorization` header of your requests:
`Authorization: Bearer <your_token>`

## Multi-Factor Authentication (MFA)

Rail Django supports TOTP (Time-based One-Time Password) for an extra layer of security.

### Activation
Enable MFA in your settings:

```python
RAIL_DJANGO_GRAPHQL = {
    "mfa_settings": {
        "enabled": True,
        "issuer_name": "MyProject",
        "enforce_for_staff": True,
    }
}
```

### MFA Flow

1. **Setup**: Use `setupTotp` to get a secret and QR code.
2. **Verification**: Confirm the device with `verifyTotp` using the code from the app.
3. **Login**: If MFA is enabled, `login` will return `mfaRequired: true`.
4. **Completion**: Use `completeMfaLogin` with the code from the authenticator app.

### Backup Codes
Upon successful MFA setup, the system provides one-time backup codes. Users should save these to regain access if they lose their device.

## Cookie Authentication
For web applications on the same domain, you can enable HTTP-only cookies for enhanced security against XSS:

```python
JWT_ALLOW_COOKIE_AUTH = True
JWT_COOKIE_SECURE = True
JWT_COOKIE_HTTPONLY = True
```

## Best Practices

1. **Short-lived Tokens**: Keep access token lifetime short (e.g., 15-30 minutes).
2. **Secure Refresh Tokens**: Refresh tokens should have longer lifetimes but be stored securely.
3. **HTTPS**: Never transmit tokens over unencrypted connections.
4. **MFA Enforcement**: Require MFA for users with elevated permissions (staff, admins).

## See Also

- [Permissions & RBAC](./permissions.md)
- [Audit Logging](../extensions/audit-logging.md)
- [Validation](./validation.md)
