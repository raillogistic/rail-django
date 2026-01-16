# Audit & Logging

## Vue d'Ensemble

Rail Django intègre un système d'audit complet qui trace les événements de sécurité, les actions utilisateurs et les modifications de données. Ce système est essentiel pour la conformité réglementaire (RGPD, SOC2) et le dépannage.

---

## Table des Matières

1. [Configuration](#configuration)
2. [Types d'Événements](#types-dévénements)
3. [Modèle AuditEvent](#modèle-auditevent)
4. [Logging Automatique](#logging-automatique)
5. [API de Logging](#api-de-logging)
6. [Rapports de Sécurité](#rapports-de-sécurité)
7. [Query GraphQL](#query-graphql)
8. [Rétention et Archivage](#rétention-et-archivage)
9. [Bonnes Pratiques](#bonnes-pratiques)

---

## Configuration

### Paramètres d'Audit

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        # Audit des vérifications de permissions
        "enable_permission_audit": True,
        "permission_audit_log_denies": True,  # Log les refus
        "permission_audit_log_all": False,    # Log tous les checks (verbose)
    },
    "middleware_settings": {
        # Active le logging des requêtes
        "enable_logging_middleware": True,
        # Types d'opérations à logger
        "log_queries": True,
        "log_mutations": True,
        "log_introspection": False,  # Évite le bruit
        "log_errors": True,
        # Performance logging
        "log_performance": True,
        "performance_threshold_ms": 1000,  # Alerter si > 1s
    },
}
```

### Activation des Extensions d'Audit

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "enable_extension_mutations": True,  # Expose les mutations d'audit
    },
}
```

---

## Types d'Événements

### Événements de Sécurité

| Type                     | Description                 |
| ------------------------ | --------------------------- |
| `login_success`          | Connexion réussie           |
| `login_failure`          | Échec de connexion          |
| `logout`                 | Déconnexion                 |
| `password_change`        | Changement de mot de passe  |
| `password_reset_request` | Demande de réinitialisation |
| `permission_denied`      | Permission refusée          |
| `mfa_setup`              | Configuration MFA           |
| `mfa_verified`           | Vérification MFA réussie    |
| `mfa_failed`             | Échec de vérification MFA   |

### Événements de Données

| Type             | Description             |
| ---------------- | ----------------------- |
| `model_created`  | Création d'un objet     |
| `model_updated`  | Modification d'un objet |
| `model_deleted`  | Suppression d'un objet  |
| `bulk_operation` | Opération en masse      |

### Événements Système

| Type               | Description                 |
| ------------------ | --------------------------- |
| `schema_rebuilt`   | Reconstruction du schéma    |
| `export_requested` | Demande d'export de données |
| `api_rate_limited` | Rate limiting déclenché     |

---

## Modèle AuditEvent

### Structure

```python
class AuditEventModel(models.Model):
    """
    Modèle de stockage des événements d'audit.

    Attributes:
        event_type: Type de l'événement.
        severity: Niveau de sévérité (info, warning, error, critical).
        user: Utilisateur concerné (nullable pour événements système).
        ip_address: Adresse IP de la requête.
        user_agent: User-Agent du client.
        action: Description de l'action.
        target_model: Modèle Django ciblé.
        target_id: ID de l'objet ciblé.
        old_values: Valeurs avant modification (JSON).
        new_values: Valeurs après modification (JSON).
        metadata: Données additionnelles (JSON).
        created_at: Horodatage de l'événement.
    """
    event_type = models.CharField(max_length=50, db_index=True)
    severity = models.CharField(max_length=20, default="info")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(blank=True)
    action = models.TextField()
    target_model = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    old_values = models.JSONField(default=dict)
    new_values = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
```

---

## Logging Automatique

### Événements de Connexion

Les connexions sont automatiquement loggées :

```python
# Connexion réussie
AuditEventModel.objects.create(
    event_type="login_success",
    severity="info",
    user=user,
    ip_address=get_client_ip(request),
    action=f"User {user.username} logged in successfully",
    metadata={
        "user_agent": request.META.get("HTTP_USER_AGENT"),
        "method": "jwt",
    }
)

# Connexion échouée (inclut la détection de brute force)
AuditEventModel.objects.create(
    event_type="login_failure",
    severity="warning",
    ip_address=get_client_ip(request),
    action=f"Failed login attempt for username: {username}",
    metadata={
        "attempt_count": attempt_count,
        "is_locked": is_locked,
    }
)
```

### Modifications de Données

Les mutations CRUD loggent automatiquement les changements :

```json
{
  "event_type": "model_updated",
  "severity": "info",
  "user": 1,
  "target_model": "store.Order",
  "target_id": "42",
  "old_values": {
    "status": "pending",
    "total": "100.00"
  },
  "new_values": {
    "status": "confirmed",
    "total": "120.00"
  },
  "metadata": {
    "mutation": "update_order",
    "fields_changed": ["status", "total"]
  }
}
```

---

## API de Logging

### Utilisation de audit_logger

```python
from rail_django.extensions.audit import audit_logger

# Log un événement simple
audit_logger.log(
    event_type="custom_action",
    severity="info",
    user=request.user,
    action="User performed custom action",
    target_model="myapp.MyModel",
    target_id="123",
)

# Log avec métadonnées
audit_logger.log(
    event_type="export_requested",
    severity="info",
    user=request.user,
    action="User requested data export",
    metadata={
        "export_format": "xlsx",
        "filters": {"status": "active"},
        "row_count": 1500,
    }
)

# Log de sécurité
audit_logger.log_security_event(
    event_type="permission_denied",
    severity="warning",
    user=request.user,
    action="Access denied to sensitive resource",
    metadata={
        "resource": "financial_report",
        "required_role": "finance",
        "user_roles": ["sales"],
    }
)
```

### Décorateur pour les Resolvers

```python
from rail_django.extensions.audit import audit_action

@audit_action(
    event_type="sensitive_operation",
    severity="info",
    include_args=True,  # Inclut les arguments dans les métadonnées
)
def resolve_sensitive_operation(root, info, **kwargs):
    """
    Cette opération est automatiquement auditée.
    """
    return perform_sensitive_operation(**kwargs)
```

### Context Manager

```python
from rail_django.extensions.audit import audit_context

def process_payment(order_id, amount):
    with audit_context(
        event_type="payment_processed",
        severity="info",
        target_model="store.Order",
        target_id=order_id,
    ) as ctx:
        # Opération
        result = payment_gateway.charge(amount)

        # Ajouter des métadonnées
        ctx.metadata["transaction_id"] = result.transaction_id
        ctx.metadata["status"] = result.status

        return result
```

---

## Rapports de Sécurité

### Dashboard de Sécurité

```python
from rail_django.extensions.audit import audit_logger

# Obtenir un rapport des 24 dernières heures
report = audit_logger.get_security_report(hours=24)
```

**Structure du Rapport :**

```python
{
    "period": {
        "start": "2026-01-15T10:30:00Z",
        "end": "2026-01-16T10:30:00Z",
    },
    "summary": {
        "total_events": 1542,
        "by_severity": {
            "info": 1200,
            "warning": 300,
            "error": 40,
            "critical": 2,
        },
    },
    "authentication": {
        "login_success": 150,
        "login_failure": 45,
        "unique_users": 85,
        "locked_accounts": 3,
        "suspicious_ips": ["192.168.1.100", "10.0.0.50"],
    },
    "permissions": {
        "denied_count": 120,
        "top_denied_resources": [
            {"resource": "financial_report", "count": 40},
            {"resource": "admin_dashboard", "count": 30},
        ],
    },
    "data_changes": {
        "creates": 200,
        "updates": 500,
        "deletes": 50,
        "by_model": {
            "store.Order": 300,
            "crm.Customer": 150,
        },
    },
}
```

### Alertes Automatiques

Configurez des seuils pour les alertes :

```python
RAIL_DJANGO_GRAPHQL = {
    "audit_settings": {
        "alert_on_suspicious_activity": True,
        "failed_login_threshold": 5,  # 5 échecs = alerte
        "failed_login_window_minutes": 10,
        "alert_callback": "myapp.alerts.send_security_alert",
    },
}
```

```python
# myapp/alerts.py
def send_security_alert(alert_type, data):
    """
    Callback pour les alertes de sécurité.

    Args:
        alert_type: Type d'alerte (brute_force, suspicious_ip, etc.)
        data: Données de l'alerte
    """
    if alert_type == "brute_force":
        send_slack_notification(
            channel="#security",
            message=f"⚠️ Tentative de brute force détectée: {data['ip_address']}",
        )
```

---

## Query GraphQL

### Liste des Événements

```graphql
query AuditEvents($filters: AuditEventFilter!) {
  audit_events(filters: $filters, order_by: ["-created_at"], limit: 100) {
    id
    event_type
    severity
    user {
      id
      username
    }
    action
    target_model
    target_id
    created_at
    metadata
  }
}
```

**Variables :**

```json
{
  "filters": {
    "event_type": { "in": ["login_success", "login_failure"] },
    "created_at": { "gte": "2026-01-15T00:00:00Z" }
  }
}
```

### Événements par Objet

```graphql
query ObjectHistory($model: String!, $objectId: ID!) {
  audit_events(
    filters: {
      target_model: { exact: $model }
      target_id: { exact: $objectId }
    }
    order_by: ["-created_at"]
  ) {
    event_type
    user {
      username
    }
    old_values
    new_values
    created_at
  }
}
```

### Statistiques de Sécurité

```graphql
query SecurityStats {
  security_report(hours: 24) {
    summary {
      total_events
      by_severity {
        info
        warning
        error
        critical
      }
    }
    authentication {
      login_success
      login_failure
      locked_accounts
    }
  }
}
```

---

## Rétention et Archivage

### Configuration de Rétention

```python
RAIL_DJANGO_GRAPHQL = {
    "audit_settings": {
        # Rétention par défaut
        "retention_days": 90,

        # Rétention par sévérité
        "retention_by_severity": {
            "info": 30,
            "warning": 90,
            "error": 365,
            "critical": 730,  # 2 ans
        },

        # Archivage avant suppression
        "archive_before_delete": True,
        "archive_backend": "s3",
        "archive_prefix": "audit-logs/",
    },
}
```

### Commande de Nettoyage

```bash
# Supprimer les anciens événements selon la politique de rétention
python manage.py cleanup_audit_logs

# Avec archivage
python manage.py cleanup_audit_logs --archive

# Simulation (dry run)
python manage.py cleanup_audit_logs --dry-run
```

### Tâche Planifiée

```python
# Celery beat schedule
CELERY_BEAT_SCHEDULE = {
    "cleanup-audit-logs": {
        "task": "rail_django.tasks.cleanup_audit_logs",
        "schedule": crontab(hour=2, minute=0),  # Chaque nuit à 2h
    },
}
```

---

## Bonnes Pratiques

### 1. Sélectivité du Logging

```python
# ✅ Logger les événements significatifs
@audit_action(event_type="payment_processed")
def process_payment(amount):
    ...

# ❌ Éviter le logging excessif
@audit_action(event_type="list_products")  # Trop de bruit
def list_products():
    ...
```

### 2. Protection des Données Sensibles

```python
# ✅ Masquer les données sensibles
audit_logger.log(
    event_type="user_updated",
    old_values={"email": "old@example.com"},
    new_values={"email": "new@example.com"},
    metadata={
        "password_changed": True,  # Indiquer sans exposer
        # "password": "..." ❌ Jamais les mots de passe
    }
)
```

### 3. Indexation pour les Requêtes

```python
# Ajoutez des index pour les queries fréquentes
class AuditEventModel(models.Model):
    event_type = models.CharField(max_length=50, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["target_model", "target_id"]),
        ]
```

### 4. Alertes Critiques

```python
# ✅ Alerter sur les événements critiques
from rail_django.extensions.audit import audit_logger

def on_critical_event(event):
    if event.severity == "critical":
        send_immediate_alert(event)

audit_logger.register_callback("critical", on_critical_event)
```

---

## Voir Aussi

- [Permissions & RBAC](../security/permissions.md) - Audit des permissions
- [Configuration](../graphql/configuration.md) - Paramètres d'audit
- [Webhooks](./webhooks.md) - Notification externe des événements
