# Authentification JWT

## Vue d'Ensemble

Rail Django intègre un système d'authentification JWT (JSON Web Token) complet pour sécuriser vos APIs GraphQL. Ce guide couvre la configuration, les mutations d'authentification, et les bonnes pratiques.

---

## Table des Matières

1. [Configuration](#configuration)
2. [Mutations d'Authentification](#mutations-dauthentification)
3. [Utilisation des Tokens](#utilisation-des-tokens)
4. [Authentification par Cookie](#authentification-par-cookie)
5. [Variables d'Environnement](#variables-denvironnement)
6. [Bonnes Pratiques](#bonnes-pratiques)

---

## Configuration

### Paramètres Principaux

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        # Requiert un JWT valide pour toutes les requêtes
        "authentication_required": True,
        # Désactive les mutations login/register si False
        "disable_security_mutations": False,
    },
    "security_settings": {
        # Active les vérifications d'authentification
        "enable_authentication": True,
        # Timeout de session en minutes
        "session_timeout_minutes": 30,
    },
}
```

### Configuration JWT

```python
# Durée de vie des tokens
JWT_ACCESS_TOKEN_LIFETIME = timedelta(minutes=30)
JWT_REFRESH_TOKEN_LIFETIME = timedelta(days=7)

# Algorithme de signature
JWT_ALGORITHM = "HS256"

# Authentification par cookie (optionnel)
JWT_ALLOW_COOKIE_AUTH = False
JWT_ENFORCE_CSRF = True
JWT_COOKIE_NAME = "access_token"
JWT_COOKIE_SECURE = True  # HTTPS uniquement
JWT_COOKIE_HTTPONLY = True
JWT_COOKIE_SAMESITE = "Lax"
```

---

## Mutations d'Authentification

### Connexion (Login)

Authentifie un utilisateur et retourne les tokens d'accès.

```graphql
mutation Login($username: String!, $password: String!) {
  login(username: $username, password: $password) {
    ok
    token # Token d'accès JWT
    refresh_token # Token de rafraîchissement
    expires_at # Date d'expiration du token
    errors # Liste des erreurs éventuelles
    user {
      id
      username
      email
      is_staff
    }
  }
}
```

**Variables :**

```json
{
  "username": "john.doe",
  "password": "mon_mot_de_passe_secret"
}
```

**Réponse Succès :**

```json
{
  "data": {
    "login": {
      "ok": true,
      "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "expires_at": "2026-01-16T12:30:00Z",
      "errors": null,
      "user": {
        "id": "1",
        "username": "john.doe",
        "email": "john@example.com",
        "is_staff": false
      }
    }
  }
}
```

**Réponse Erreur :**

```json
{
  "data": {
    "login": {
      "ok": false,
      "token": null,
      "errors": ["Identifiants invalides"]
    }
  }
}
```

### Rafraîchissement du Token

Obtient un nouveau token d'accès à partir du refresh token.

```graphql
mutation RefreshToken($refreshToken: String!) {
  refresh_token(refresh_token: $refreshToken) {
    ok
    token # Nouveau token d'accès
    refresh_token # Nouveau refresh token (rotation optionnelle)
    expires_at
    errors
  }
}
```

**Variables :**

```json
{
  "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Déconnexion (Logout)

Invalide le token actuel (si la liste noire est activée).

```graphql
mutation Logout {
  logout {
    ok
  }
}
```

### Inscription (Register)

Crée un nouveau compte utilisateur.

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

**Variables :**

```json
{
  "input": {
    "username": "nouveau_user",
    "email": "nouveau@example.com",
    "password": "MotDePasse123!",
    "password_confirm": "MotDePasse123!"
  }
}
```

### Utilisateur Courant (Me)

Récupère les informations de l'utilisateur authentifié.

```graphql
query Me {
  me {
    id
    username
    email
    first_name
    last_name
    is_staff
    is_superuser
    permissions # Liste des permissions Django
    groups {
      id
      name
    }
  }
}
```

---

## Utilisation des Tokens

### En-tête Authorization

Ajoutez le token JWT dans l'en-tête `Authorization` de chaque requête :

```http
POST /graphql/gql/ HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json

{
  "query": "{ me { id username } }"
}
```

### Exemple JavaScript (Fetch)

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

### Exemple Apollo Client

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

### Gestion de l'Expiration

Implémentez un intercepteur pour rafraîchir automatiquement les tokens expirés :

```typescript
import { onError } from "@apollo/client/link/error";

const errorLink = onError(({ graphQLErrors, operation, forward }) => {
  if (graphQLErrors) {
    for (const err of graphQLErrors) {
      if (err.message.includes("Signature has expired")) {
        // Rafraîchir le token
        const refreshToken = localStorage.getItem("refresh_token");
        // ... appeler refresh_token mutation
        // ... mettre à jour le token stocké
        // ... réessayer la requête originale
        return forward(operation);
      }
    }
  }
});
```

---

## Authentification par Cookie

Pour les applications web, vous pouvez utiliser des cookies HTTP-only au lieu des en-têtes Authorization.

### Activation

```python
# settings.py
JWT_ALLOW_COOKIE_AUTH = True
JWT_ENFORCE_CSRF = True  # Recommandé pour les cookies
JWT_COOKIE_NAME = "access_token"
JWT_COOKIE_SECURE = True  # Uniquement HTTPS
JWT_COOKIE_HTTPONLY = True  # Inaccessible via JavaScript
JWT_COOKIE_SAMESITE = "Lax"  # Protection CSRF basique
```

### Fonctionnement

1. La mutation `login` définit le cookie automatiquement.
2. Le navigateur envoie le cookie avec chaque requête.
3. CSRF protection s'applique aux mutations.

### Protection CSRF

Lorsque `JWT_ENFORCE_CSRF=True`, incluez le token CSRF dans les requêtes mutation :

```javascript
// Lire le token CSRF depuis le cookie Django
function getCsrfToken() {
  return document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="))
    ?.split("=")[1];
}

const response = await fetch("/graphql/gql/", {
  method: "POST",
  credentials: "include", // Envoie les cookies
  headers: {
    "Content-Type": "application/json",
    "X-CSRFToken": getCsrfToken(),
  },
  body: JSON.stringify({ query: "mutation { ... }" }),
});
```

---

## Variables d'Environnement

| Variable                     | Description                        | Défaut              |
| ---------------------------- | ---------------------------------- | ------------------- |
| `JWT_SECRET_KEY`             | Clé secrète pour signer les tokens | `DJANGO_SECRET_KEY` |
| `JWT_ACCESS_TOKEN_LIFETIME`  | Durée de vie du token d'accès      | `30 minutes`        |
| `JWT_REFRESH_TOKEN_LIFETIME` | Durée de vie du refresh token      | `7 jours`           |
| `JWT_ALLOW_COOKIE_AUTH`      | Active l'auth par cookie           | `False`             |
| `JWT_ENFORCE_CSRF`           | Applique CSRF pour cookies         | `True`              |

---

## Bonnes Pratiques

### 1. Sécurité des Tokens

```python
# ✅ Utilisez une clé secrète forte et unique
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

# ✅ Durée de vie courte pour les tokens d'accès
JWT_ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)

# ✅ Rotation des refresh tokens
JWT_ROTATE_REFRESH_TOKENS = True
JWT_BLACKLIST_AFTER_ROTATION = True
```

### 2. Stockage Côté Client

```javascript
// ✅ Pour applications SPA : LocalStorage avec refresh token flow
localStorage.setItem("access_token", token);

// ✅ Pour applications web classiques : Cookies HTTP-only
// (géré automatiquement par le serveur)

// ❌ Évitez de stocker des tokens sensibles dans SessionStorage
// ❌ N'exposez jamais le refresh token dans l'URL
```

### 3. Gestion des Erreurs

Gérez les erreurs d'authentification de manière cohérente :

```python
# Les erreurs retournées incluent :
# - "Identifiants invalides"
# - "Signature has expired"
# - "Token is invalid"
# - "User account is disabled"
```

### 4. Audit

Activez le logging des événements d'authentification :

```python
RAIL_DJANGO_GRAPHQL = {
    "middleware_settings": {
        "log_queries": True,
        "log_mutations": True,
    }
}
```

📖 Voir [Audit & Logging](../extensions/audit.md) pour plus de détails.

---

## Dépannage

### Erreur : "Signature has expired"

**Cause :** Le token JWT a expiré.

**Solution :** Utilisez la mutation `refresh_token` pour obtenir un nouveau token d'accès.

### Erreur : "Token is invalid"

**Cause :** Token malformé, modifié, ou clé secrète différente.

**Solution :**

1. Vérifiez que `JWT_SECRET_KEY` est cohérente entre environnements.
2. Demandez à l'utilisateur de se reconnecter.

### Erreur : "Authentication required"

**Cause :** Requête sans token vers un endpoint protégé.

**Solution :** Ajoutez l'en-tête `Authorization: Bearer <token>`.

---

## Voir Aussi

- [Permissions & RBAC](./permissions.md)
- [Authentification Multi-Facteurs](./mfa.md)
- [Audit & Logging](../extensions/audit.md)
