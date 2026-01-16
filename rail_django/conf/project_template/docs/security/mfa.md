# Authentification Multi-Facteurs (MFA)

## Vue d'Ensemble

Rail Django intègre un système d'authentification multi-facteurs (MFA) basé sur TOTP (Time-based One-Time Password) compatible avec les applications d'authentification standard (Google Authenticator, Authy, Microsoft Authenticator).

---

## Table des Matières

1. [Configuration](#configuration)
2. [Flux de Configuration TOTP](#flux-de-configuration-totp)
3. [Mutations GraphQL](#mutations-graphql)
4. [Enforcement MFA](#enforcement-mfa)
5. [Bonnes Pratiques](#bonnes-pratiques)

---

## Configuration

### Paramètres MFA

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        # Active les mutations MFA
        "enable_extension_mutations": True,
    },
    "mfa_settings": {
        "enabled": True,
        # Nombre de chiffres du code TOTP
        "totp_digits": 6,
        # Intervalle de validité en secondes
        "totp_interval": 30,
        # Tolerance (nombre de périodes avant/après)
        "totp_tolerance": 1,
        # Forcer MFA pour les staff users
        "enforce_for_staff": True,
        # Forcer MFA pour les superusers
        "enforce_for_superusers": True,
        # Nombre max de devices par utilisateur
        "max_devices_per_user": 5,
        # Nom de l'émetteur dans l'app auth
        "issuer_name": "MonApplication",
    },
}
```

---

## Flux de Configuration TOTP

### Étape 1 : Initialisation

L'utilisateur demande la configuration d'un nouveau device TOTP :

```graphql
mutation SetupTotp($deviceName: String!) {
  setup_totp(device_name: $deviceName) {
    ok
    device_id # ID du device créé (en attente de vérification)
    secret # Clé secrète (à ne jamais afficher directement)
    qr_code_url # URL du QR code à scanner
    provisioning_uri # URI otpauth:// pour import manuel
    errors
  }
}
```

**Variables :**

```json
{
  "deviceName": "Mon iPhone"
}
```

**Réponse :**

```json
{
  "data": {
    "setup_totp": {
      "ok": true,
      "device_id": "1",
      "secret": "JBSWY3DPEHPK3PXP",
      "qr_code_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...",
      "provisioning_uri": "otpauth://totp/MonApplication:john.doe?secret=JBSWY3DPEHPK3PXP&issuer=MonApplication",
      "errors": null
    }
  }
}
```

### Étape 2 : Affichage du QR Code

Affichez le QR code pour que l'utilisateur le scanne avec son app d'authentification :

```html
<img
  src="{{ qr_code_url }}"
  alt="Scanner ce QR code avec votre app d'authentification"
/>

<!-- Alternative : URI manuelle -->
<p>Ou entrez manuellement cette clé : <code>{{ secret }}</code></p>
```

### Étape 3 : Vérification

L'utilisateur entre le code généré par son app pour confirmer la configuration :

```graphql
mutation VerifyTotp($deviceId: ID!, $token: String!) {
  verify_totp(device_id: $deviceId, token: $token) {
    ok
    device {
      id
      name
      confirmed # true après vérification réussie
      created_at
    }
    backup_codes # Codes de secours (à sauvegarder)
    errors
  }
}
```

**Variables :**

```json
{
  "deviceId": "1",
  "token": "123456"
}
```

**Réponse Succès :**

```json
{
  "data": {
    "verify_totp": {
      "ok": true,
      "device": {
        "id": "1",
        "name": "Mon iPhone",
        "confirmed": true,
        "created_at": "2026-01-16T10:30:00Z"
      },
      "backup_codes": ["ABCD-1234-EFGH", "IJKL-5678-MNOP", "QRST-9012-UVWX"],
      "errors": null
    }
  }
}
```

---

## Mutations GraphQL

### Liste des Devices MFA

```graphql
query MyMfaDevices {
  my_mfa_devices {
    id
    name
    confirmed
    last_used_at
    created_at
  }
}
```

### Suppression d'un Device

```graphql
mutation RemoveMfaDevice($deviceId: ID!) {
  remove_mfa_device(device_id: $deviceId) {
    ok
    errors
  }
}
```

### Vérification lors de la Connexion

Si MFA est activé, la mutation `login` retourne `mfa_required: true` :

```graphql
mutation Login($username: String!, $password: String!) {
  login(username: $username, password: $password) {
    ok
    mfa_required # true si l'utilisateur a des devices MFA
    mfa_session_token # Token temporaire pour la vérification MFA
    token # null si mfa_required
    errors
  }
}
```

Puis l'utilisateur doit compléter avec la vérification MFA :

```graphql
mutation CompleteMfaLogin($sessionToken: String!, $totpCode: String!) {
  complete_mfa_login(session_token: $sessionToken, totp_code: $totpCode) {
    ok
    token # Token JWT final
    refresh_token
    user {
      id
      username
    }
    errors
  }
}
```

### Utilisation des Codes de Secours

Si l'utilisateur n'a pas accès à son device :

```graphql
mutation CompleteMfaLogin($sessionToken: String!, $backupCode: String!) {
  complete_mfa_login(session_token: $sessionToken, backup_code: $backupCode) {
    ok
    token
    remaining_backup_codes # Nombre de codes restants
    errors
  }
}
```

### Régénération des Codes de Secours

```graphql
mutation RegenerateBackupCodes($totpCode: String!) {
  regenerate_backup_codes(totp_code: $totpCode) {
    ok
    backup_codes # Nouveaux codes (les anciens sont invalidés)
    errors
  }
}
```

---

## Enforcement MFA

### Middleware d'Enforcement

Lorsque MFA est forcé, les utilisateurs sans device MFA configuré sont bloqués sur les mutations sensibles :

```python
RAIL_DJANGO_GRAPHQL = {
    "mfa_settings": {
        "enforce_for_staff": True,
        # Liste des mutations autorisées sans MFA
        "exempt_mutations": [
            "setup_totp",
            "verify_totp",
            "logout",
        ],
    },
}
```

### Vérification dans les Resolvers

```python
from rail_django.extensions.auth import require_mfa

@require_mfa
def resolve_sensitive_operation(root, info, **kwargs):
    """
    Cette opération requiert que l'utilisateur ait MFA activé.
    """
    # ... logique sensible
```

### Query de Statut MFA

```graphql
query MfaStatus {
  me {
    id
    username
    mfa_enabled # true si au moins un device confirmé
    mfa_devices_count
    mfa_required # true si enforcement s'applique
  }
}
```

---

## Bonnes Pratiques

### 1. Stockage des Codes de Secours

Affichez les codes de secours une seule fois et demandez à l'utilisateur de les sauvegarder :

```html
<div class="backup-codes-warning">
  <h3>⚠️ Sauvegardez ces codes de secours</h3>
  <p>Ces codes ne seront plus affichés. Conservez-les en lieu sûr.</p>
  <ul>
    {{#each backupCodes}}
    <li><code>{{ this }}</code></li>
    {{/each}}
  </ul>
  <button onclick="window.print()">Imprimer</button>
</div>
```

### 2. Nombre de Devices

Autorisez plusieurs devices pour éviter les problèmes d'accès :

```python
"mfa_settings": {
    "max_devices_per_user": 3,  # Permet un backup
}
```

### 3. Délai de Grâce

Accordez un délai pour configurer MFA après activation de l'enforcement :

```python
"mfa_settings": {
    "enforcement_grace_period_hours": 24,
}
```

### 4. Logging des Événements MFA

```python
"mfa_settings": {
    "log_mfa_events": True,  # Log succès/échecs
},
```

📖 Les événements MFA sont tracés dans le système d'audit. Voir [Audit & Logging](../extensions/audit.md).

---

## Voir Aussi

- [Authentification JWT](./authentication.md)
- [Permissions & RBAC](./permissions.md)
- [Audit & Logging](../extensions/audit.md)
