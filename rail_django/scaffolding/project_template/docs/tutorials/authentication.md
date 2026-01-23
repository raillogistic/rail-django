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

```
┌──────────┐     1. Login      ┌──────────┐
│  Client  │ ─────────────────▶│  Server  │
│          │◀───────────────── │          │
└──────────┘  2. JWT + Refresh └──────────┘
      │
      │ 3. Request + JWT
      ▼
┌──────────┐                   ┌──────────┐
│  Client  │ ─────────────────▶│  Server  │
│          │◀───────────────── │          │
└──────────┘     4. Response   └──────────┘
```

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

**Response:**
```json
{
  "data": {
    "login": {
      "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
      "refreshToken": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
      "user": {
        "id": "1",
        "username": "john",
        "email": "john@example.com"
      }
    }
  }
}
```

### Step 2: Use the Token

Include the token in the `Authorization` header:

```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/graphql/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \
  -d '{"query": "query { me { username email } }"}'
```

### Step 3: Refresh Token

When the access token expires, use the refresh token:

```graphql
mutation {
  refreshToken(refreshToken: "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...") {
    token
    refreshToken
  }
}
```

### Step 4: Logout

Invalidate the refresh token:

```graphql
mutation {
  logout(refreshToken: "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...") {
    ok
  }
}
```

---

## Configuration

### JWT Settings

```python
# root/settings/base.py

RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_authentication": True,
    }
}

# JWT Configuration
JWT_ALGORITHM = "HS256"
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)
JWT_ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
JWT_REFRESH_TOKEN_LIFETIME = timedelta(days=7)

# Cookie-based JWT (optional)
JWT_ALLOW_COOKIE_AUTH = True
JWT_ENFORCE_CSRF = True
JWT_COOKIE_NAME = "access_token"
JWT_COOKIE_SECURE = True  # Set True in production
JWT_COOKIE_HTTPONLY = True
JWT_COOKIE_SAMESITE = "Lax"
```

### Require Authentication

Require authentication for all queries/mutations:

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "authentication_required": True
    }
}
```

---

## User Registration

### Create Registration Mutation

Rail Django can auto-generate registration if enabled, or you can create custom:

```graphql
mutation {
  register(input: {
    username: "newuser"
    email: "new@example.com"
    password: "securepassword123"
    firstName: "New"
    lastName: "User"
  }) {
    ok
    user {
      id
      username
      email
    }
    errors {
      field
      message
    }
  }
}
```

### Email Verification

If email verification is enabled:

```graphql
mutation {
  verifyEmail(token: "verification-token-from-email") {
    ok
    message
  }
}
```

---

## Password Management

### Change Password

For authenticated users:

```graphql
mutation {
  changePassword(
    oldPassword: "currentpassword"
    newPassword: "newsecurepassword123"
  ) {
    ok
    message
  }
}
```

### Forgot Password

Request password reset:

```graphql
mutation {
  forgotPassword(email: "user@example.com") {
    ok
    message
  }
}
```

### Reset Password

Complete reset with token from email:

```graphql
mutation {
  resetPassword(
    token: "reset-token-from-email"
    newPassword: "newsecurepassword123"
  ) {
    ok
    message
  }
}
```

---

## Multi-Factor Authentication (MFA)

### Enable TOTP

Set up authenticator app:

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

Confirm setup with code from app:

```graphql
mutation {
  verifyTotp(deviceId: "1", token: "123456") {
    ok
    message
  }
}
```

### Login with MFA

When MFA is enabled, login returns a challenge:

```graphql
mutation {
  login(username: "john", password: "secret123") {
    token            # null if MFA required
    mfaRequired      # true
    mfaChallenge     # Challenge token
  }
}
```

Complete with TOTP:

```graphql
mutation {
  completeMfaLogin(
    challengeToken: "challenge-token"
    totpCode: "123456"
  ) {
    token
    refreshToken
    user {
      username
    }
  }
}
```

### Manage MFA Devices

List devices:
```graphql
query {
  me {
    mfaDevices {
      id
      name
      createdAt
      lastUsedAt
    }
  }
}
```

Remove device:
```graphql
mutation {
  removeTotpDevice(deviceId: "1") {
    ok
  }
}
```

---

## Current User Query

Get authenticated user info:

```graphql
query {
  me {
    id
    username
    email
    firstName
    lastName
    isStaff
    isSuperuser
    groups {
      name
    }
    permissions
    mfaEnabled
  }
}
```

---

## Cookie-Based Authentication

For web applications, use HTTP-only cookies:

### Configuration

```python
JWT_ALLOW_COOKIE_AUTH = True
JWT_ENFORCE_CSRF = True  # Require CSRF token
JWT_COOKIE_SECURE = True  # HTTPS only
JWT_COOKIE_HTTPONLY = True  # Not accessible via JS
JWT_COOKIE_SAMESITE = "Lax"
```

### Login Sets Cookie

When using cookie auth, login sets the cookie automatically:

```graphql
mutation {
  login(username: "john", password: "secret") {
    ok
    user {
      username
    }
    # Cookie is set in response headers
  }
}
```

### CSRF Protection

Include CSRF token in requests:

```javascript
// Get CSRF token from cookie
const csrfToken = document.cookie
  .split('; ')
  .find(row => row.startsWith('csrftoken='))
  ?.split('=')[1];

// Include in request
fetch('/graphql/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': csrfToken,
  },
  credentials: 'include',  // Send cookies
  body: JSON.stringify({ query: '...' })
});
```

---

## Frontend Integration

### React Example

```tsx
import { useState } from 'react';
import { useMutation, gql } from '@apollo/client';

const LOGIN_MUTATION = gql`
  mutation Login($username: String!, $password: String!) {
    login(username: $username, password: $password) {
      token
      refreshToken
      user {
        id
        username
      }
    }
  }
`;

function LoginForm() {
  const [login, { loading, error }] = useMutation(LOGIN_MUTATION);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const { data } = await login({
        variables: { username, password }
      });

      // Store tokens
      localStorage.setItem('token', data.login.token);
      localStorage.setItem('refreshToken', data.login.refreshToken);

      // Redirect to app
      window.location.href = '/dashboard';
    } catch (err) {
      console.error('Login failed:', err);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        type="text"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        placeholder="Username"
      />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
      />
      <button type="submit" disabled={loading}>
        {loading ? 'Loading...' : 'Login'}
      </button>
      {error && <p className="error">{error.message}</p>}
    </form>
  );
}
```

### Apollo Client Setup

```tsx
import {
  ApolloClient,
  InMemoryCache,
  createHttpLink,
  ApolloLink,
} from '@apollo/client';
import { setContext } from '@apollo/client/link/context';

const httpLink = createHttpLink({
  uri: '/graphql/',
});

const authLink = setContext((_, { headers }) => {
  const token = localStorage.getItem('token');
  return {
    headers: {
      ...headers,
      authorization: token ? `Bearer ${token}` : '',
    },
  };
});

// Token refresh link
const refreshLink = new ApolloLink((operation, forward) => {
  return forward(operation).map((response) => {
    // Check for auth errors
    if (response.errors?.some(e => e.message.includes('expired'))) {
      // Trigger token refresh
      refreshToken();
    }
    return response;
  });
});

const client = new ApolloClient({
  link: ApolloLink.from([authLink, refreshLink, httpLink]),
  cache: new InMemoryCache(),
});
```

---

## Security Best Practices

### ✅ Do

1. **Use HTTPS in production**
   ```python
   JWT_COOKIE_SECURE = True
   ```

2. **Set short token lifetimes**
   ```python
   JWT_ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
   ```

3. **Use HTTP-only cookies for web apps**
   ```python
   JWT_COOKIE_HTTPONLY = True
   ```

4. **Enable CSRF protection**
   ```python
   JWT_ENFORCE_CSRF = True
   ```

5. **Use strong secret keys**
   ```python
   JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
   ```

### ❌ Don't

1. **Store tokens in localStorage for sensitive apps**
   - Use HTTP-only cookies instead

2. **Use long-lived access tokens**
   - Use refresh tokens for persistence

3. **Disable CSRF protection**
   - Required for cookie-based auth

4. **Expose token in URL parameters**
   - Always use headers or cookies

---

## Troubleshooting

### "Signature has expired"

Token has expired. Use refresh token:

```graphql
mutation {
  refreshToken(refreshToken: "...") {
    token
  }
}
```

### "Authentication required"

Request missing token. Add header:

```
Authorization: Bearer <token>
```

### "Invalid token"

Token is malformed or tampered. Get new token via login.

### CSRF verification failed

Include CSRF token in request:

```
X-CSRFToken: <csrf-token>
```

---

## Next Steps

- [Permissions Tutorial](./permissions.md) - Role-based access control
- [Audit Logging](./audit-logging.md) - Track authentication events
- [Configuration](./configuration.md) - All security settings
