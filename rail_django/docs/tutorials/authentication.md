# Authentication Tutorial

This tutorial covers implementing authentication in your Rail Django API, including JWT tokens, session authentication, and multi-factor authentication.

## Overview

Rail Django supports multiple authentication methods:

1. **JWT (JSON Web Tokens)** - Stateless token-based auth
2. **Session Authentication** - Django's built-in session auth
3. **Cookie-based JWT** - JWTs stored in HTTP-only cookies
4. **Multi-Factor Authentication (MFA)** - TOTP-based 2FA

---

## JWT Authentication

### How It Works

1. **Login**: Client sends username and password.
2. **Tokens**: Server returns a short-lived access token and a long-lived refresh token.
3. **Request**: Client sends access token in the `Authorization` header.
4. **Refresh**: When access token expires, client uses refresh token to get a new one.

### Step 1: Login

Send username and password to get tokens:

```graphql
mutation {
  login(username: "john", password: "secret123") {
    token           # Access token (short-lived)
    refreshToken    # Refresh token (long-lived)
    user {
      id
      username
      email
    }
  }
}
```

### Step 2: Use the Token

Include the token in the `Authorization` header:

```
Authorization: Bearer <your_token>
```

### Step 3: Refresh Token

When the access token expires, use the refresh token:

```graphql
mutation {
  refreshToken(refreshToken: "<your_refresh_token>") {
    token
    refreshToken
  }
}
```

---

## Multi-Factor Authentication (MFA)

### Enable TOTP

Set up an authenticator app (Google Authenticator, Authy, etc.):

```graphql
mutation {
  setupTotp(deviceName: "My iPhone") {
    ok
    totpSecret      # Secret key for manual entry
    qrCodeUrl       # URL to generate QR code
    deviceId        # Device ID for verification
  }
}
```

### Verify TOTP Device

Confirm setup with the code from your app:

```graphql
mutation {
  verifyTotp(deviceId: "1", token: "123456") {
    ok
    message
  }
}
```

### Login with MFA

When MFA is enabled, `login` returns `mfaRequired: true`. You must then complete the login with `completeMfaLogin`.

```graphql
mutation {
  completeMfaLogin(
    challengeToken: "<challenge_token>",
    totpCode: "123456"
  ) {
    token
    user { username }
  }
}
```

## Next Steps

- [Permissions Tutorial](./permissions.md) - Secure your mutations.
- [Audit Logging](../extensions/audit-logging.md) - Track security events.
