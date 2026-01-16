# Configuration Complète

## Vue d'Ensemble

Ce document est la référence complète de tous les paramètres de configuration de Rail Django. Tous les paramètres sont définis dans `RAIL_DJANGO_GRAPHQL` de votre fichier `settings.py`.

---

## Table des Matières

1. [Structure Générale](#structure-générale)
2. [schema_settings](#schema_settings)
3. [type_generation_settings](#type_generation_settings)
4. [query_settings](#query_settings)
5. [mutation_settings](#mutation_settings)
6. [subscription_settings](#subscription_settings)
7. [performance_settings](#performance_settings)
8. [security_settings](#security_settings)
9. [middleware_settings](#middleware_settings)
10. [error_handling](#error_handling)
11. [custom_scalars](#custom_scalars)
12. [Multi-Schema](#multi-schema)

---

## Structure Générale

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": { ... },
    "type_generation_settings": { ... },
    "query_settings": { ... },
    "mutation_settings": { ... },
    "subscription_settings": { ... },
    "performance_settings": { ... },
    "security_settings": { ... },
    "middleware_settings": { ... },
    "error_handling": { ... },
    "custom_scalars": { ... },
    "monitoring_settings": { ... },
    "schema_registry": { ... },
}
```

---

## schema_settings

Configuration globale du schéma GraphQL.

```python
"schema_settings": {
    # ─── Exclusions ───
    # Apps Django à ignorer lors de la génération
    "excluded_apps": ["admin", "contenttypes", "sessions"],
    # Modèles spécifiques à ignorer ("app.Model" ou "Model")
    "excluded_models": ["auth.Permission"],

    # ─── Fonctionnalités du Schéma ───
    # Permet la query __schema / __type
    "enable_introspection": True,
    # Active l'interface GraphiQL
    "enable_graphiql": True,
    # Reconstruire le schéma après save/delete mod (dev only)
    "auto_refresh_on_model_change": False,
    # Reconstruire après migrations
    "auto_refresh_on_migration": True,
    # Construire le schéma au démarrage
    "prebuild_on_startup": False,

    # ─── Authentification ───
    # Requiert un JWT valide pour toutes les requêtes
    "authentication_required": True,
    # Désactive login/register/logout mutations
    "disable_security_mutations": False,
    # Active les mutations des extensions (audit, health, etc.)
    "enable_extension_mutations": True,

    # ─── Pagination ───
    # Active les champs de pagination (offset/limit)
    "enable_pagination": True,

    # ─── Naming ───
    # Convertit les noms en camelCase (false = snake_case)
    "auto_camelcase": False,

    # ─── Metadata ───
    # Expose les queries de métadonnées pour les UI dynamiques
    "show_metadata": False,

    # ─── Extensions ───
    # Classes Query additionnelles (dotted path)
    "query_extensions": [
        "myapp.schema.CustomQuery",
    ],
    # Classes Mutation additionnelles
    "mutation_extensions": [],

    # ─── Allowlists (optionnel) ───
    # Si défini, seuls ces champs root sont exposés
    "query_field_allowlist": None,  # ["users", "products"]
    "mutation_field_allowlist": None,
    "subscription_field_allowlist": None,
}
```

---

## type_generation_settings

Contrôle la génération des types GraphQL.

```python
"type_generation_settings": {
    # Champs à exclure par modèle
    "exclude_fields": {
        "auth.User": ["password"],
        "store.Product": ["internal_notes"],
    },
    # Alias legacy
    "excluded_fields": {},

    # Champs à inclure (None = tous)
    "include_fields": None,

    # Mappings de types personnalisés
    "custom_field_mappings": {
        # Django Field Class: Graphene Scalar
    },

    # Génère les inputs de filtrage
    "generate_filters": True,
    "enable_filtering": True,  # Alias

    # Naming
    "auto_camelcase": False,

    # Utilise help_text des modèles comme descriptions
    "generate_descriptions": True,
}
```

---

## query_settings

Configuration des requêtes GraphQL.

```python
"query_settings": {
    # ─── Génération ───
    "generate_filters": True,
    "generate_ordering": True,
    "generate_pagination": True,

    # ─── Exécution ───
    "enable_pagination": True,
    "enable_ordering": True,

    # ─── Style ───
    # Utilise les connections Relay au lieu de listes
    "use_relay": False,

    # ─── Pagination ───
    "default_page_size": 20,
    "max_page_size": 100,

    # ─── Grouping ───
    "max_grouping_buckets": 200,

    # ─── Property Ordering ───
    # Limite les résultats quand on trie par propriété Python
    "max_property_ordering_results": 2000,

    # ─── Lookups Additionnels ───
    # Permet de fetch par d'autres champs que l'ID
    "additional_lookup_fields": {
        "store.Product": ["sku", "slug"],
        "auth.User": ["username", "email"],
    },

    # ─── Permissions ───
    "require_model_permissions": True,
    "model_permission_codename": "view",
}
```

---

## mutation_settings

Configuration des mutations GraphQL.

```python
"mutation_settings": {
    # ─── Génération ───
    "generate_create": True,
    "generate_update": True,
    "generate_delete": True,
    "generate_bulk": False,

    # ─── Exécution ───
    "enable_create": True,
    "enable_update": True,
    "enable_delete": True,
    "enable_bulk_operations": False,

    # ─── Méthodes ───
    # Expose les méthodes de modèle comme mutations
    "enable_method_mutations": True,

    # ─── Permissions ───
    "require_model_permissions": True,
    "model_permission_codenames": {
        "create": "add",
        "update": "change",
        "delete": "delete",
    },

    # ─── Bulk ───
    "bulk_batch_size": 100,

    # ─── Champs Requis ───
    "required_update_fields": {},

    # ─── Relations Imbriquées ───
    "enable_nested_relations": True,
    "nested_relations_config": {},
    "nested_field_config": {},
}
```

---

## subscription_settings

Configuration des subscriptions temps réel.

```python
"subscription_settings": {
    # Active la génération des subscriptions
    "enable_subscriptions": True,

    # Types d'événements
    "enable_create": True,
    "enable_update": True,
    "enable_delete": True,

    # Active les filtres sur les subscriptions
    "enable_filters": True,

    # Allowlist/Blocklist de modèles
    "include_models": [],  # Vide = tous
    "exclude_models": ["audit.AuditEvent"],
}
```

---

## performance_settings

Optimisation des performances.

```python
"performance_settings": {
    # ─── Optimisation QuerySet ───
    "enable_query_optimization": True,
    "enable_select_related": True,
    "enable_prefetch_related": True,
    "enable_only_fields": True,
    "enable_defer_fields": False,

    # ─── DataLoader ───
    "enable_dataloader": True,
    "dataloader_batch_size": 100,

    # ─── Limites ───
    "max_query_depth": 10,
    "max_query_complexity": 1000,

    # ─── Coût ───
    "enable_query_cost_analysis": False,

    # ─── Timeout ───
    "query_timeout": 30,
}
```

---

## security_settings

Configuration de la sécurité.

```python
"security_settings": {
    # ─── Auth ───
    "enable_authentication": True,
    "enable_authorization": True,

    # ─── Policy Engine ───
    "enable_policy_engine": True,

    # ─── Permission Cache ───
    "enable_permission_cache": True,
    "permission_cache_ttl_seconds": 300,

    # ─── Permission Audit ───
    "enable_permission_audit": False,
    "permission_audit_log_all": False,
    "permission_audit_log_denies": True,

    # ─── Rate Limiting ───
    "enable_rate_limiting": False,
    "rate_limit_requests_per_minute": 60,
    "rate_limit_requests_per_hour": 1000,

    # ─── Depth Limiting ───
    "enable_query_depth_limiting": True,

    # ─── CORS ───
    "allowed_origins": ["*"],
    "enable_csrf_protection": True,
    "enable_cors": True,

    # ─── Field Permissions ───
    "enable_field_permissions": True,
    "field_permission_input_mode": "reject",  # ou "strip"
    "enable_object_permissions": True,

    # ─── Input Validation ───
    "enable_input_validation": True,
    "enable_sql_injection_protection": True,
    "enable_xss_protection": True,

    # ─── HTML dans Inputs ───
    "input_allow_html": False,
    "input_allowed_html_tags": ["p", "br", "strong", "em", ...],
    "input_allowed_html_attributes": {"*": ["class"], "a": ["href"], ...},

    # ─── Limites Strings ───
    "input_max_string_length": None,
    "input_truncate_long_strings": False,
    "input_failure_severity": "high",
    "input_pattern_scan_limit": 10000,

    # ─── Session ───
    "session_timeout_minutes": 30,

    # ─── Upload ───
    "max_file_upload_size": 10 * 1024 * 1024,  # 10MB
    "allowed_file_types": [".jpg", ".jpeg", ".png", ".pdf", ".txt"],
}
```

---

## middleware_settings

Configuration du middleware GraphQL.

```python
"middleware_settings": {
    # ─── Activation ───
    "enable_authentication_middleware": True,
    "enable_logging_middleware": True,
    "enable_performance_middleware": True,
    "enable_error_handling_middleware": True,
    "enable_rate_limiting_middleware": True,
    "enable_validation_middleware": True,
    "enable_field_permission_middleware": True,
    "enable_cors_middleware": True,
    "enable_query_complexity_middleware": True,

    # ─── Logging ───
    "log_queries": True,
    "log_mutations": True,
    "log_introspection": False,
    "log_errors": True,

    # ─── Performance ───
    "log_performance": True,
    "performance_threshold_ms": 1000,
}
```

---

## error_handling

Gestion des erreurs.

```python
"error_handling": {
    # Inclut les détails d'erreur
    "enable_detailed_errors": False,  # True en dev

    # Logging
    "enable_error_logging": True,
    "enable_error_reporting": True,

    # Sentry
    "enable_sentry_integration": False,

    # Masquage
    "mask_internal_errors": True,
    "include_stack_trace": False,

    # Format
    "error_code_prefix": "RAIL_GQL",
    "max_error_message_length": 500,

    # Catégorisation
    "enable_error_categorization": True,
    "enable_error_metrics": True,

    # Log Level
    "log_level": "ERROR",
}
```

---

## custom_scalars

Scalaires GraphQL personnalisés.

```python
"custom_scalars": {
    "DateTime": {"enabled": True},
    "Date": {"enabled": True},
    "Time": {"enabled": True},
    "JSON": {"enabled": True},
    "UUID": {"enabled": True},
    "Email": {"enabled": True},
    "URL": {"enabled": True},
    "Phone": {"enabled": True},
    "Decimal": {"enabled": True},
    "Binary": {"enabled": True},
}
```

---

## Multi-Schema

Configuration de schémas multiples.

```python
# Schémas distincts avec configurations différentes
RAIL_DJANGO_GRAPHQL_SCHEMAS = {
    # Schéma d'authentification (public)
    "auth": {
        "schema_settings": {
            "authentication_required": False,
            "enable_graphiql": False,
            "query_field_allowlist": ["me"],
            "mutation_field_allowlist": ["login", "register", "refresh_token"],
        },
        "mutation_settings": {
            "generate_create": False,
            "generate_update": False,
        },
    },

    # Schéma principal (authentifié)
    "default": {
        "schema_settings": {
            "authentication_required": True,
        },
    },

    # Schéma admin (privilégié)
    "admin": {
        "schema_settings": {
            "authentication_required": True,
            "enable_graphiql": True,
        },
        "mutation_settings": {
            "enable_bulk_operations": True,
        },
    },
}
```

### Endpoints Générés

- `/graphql/auth/` - Schéma auth
- `/graphql/gql/` - Schéma default
- `/graphql/admin/` - Schéma admin

### Enregistrement des Schémas

Les schémas sont enregistrés depuis deux sources :

1. **Discovery automatique** : Modules `schemas.py`, `graphql_schema.py` avec `register_schema()`
2. **Settings fallback** : Entrées dans `RAIL_DJANGO_GRAPHQL_SCHEMAS`

### Désactivation d'un Schéma

```python
RAIL_DJANGO_GRAPHQL_SCHEMAS = {
    "admin": {
        "enabled": False,  # Désactivé
    },
}
```

---

## Variables d'Environnement

| Variable                      | Description                   | Défaut                     |
| ----------------------------- | ----------------------------- | -------------------------- |
| `DJANGO_SETTINGS_MODULE`      | Module de settings            | `root.settings.dev`        |
| `DJANGO_SECRET_KEY`           | Clé secrète Django            | (requis)                   |
| `DATABASE_URL`                | URL de connexion DB           | (requis)                   |
| `REDIS_URL`                   | URL Redis (cache, rate limit) | `redis://localhost:6379/0` |
| `JWT_SECRET_KEY`              | Clé pour signer les JWT       | `DJANGO_SECRET_KEY`        |
| `GRAPHQL_PERFORMANCE_ENABLED` | Active les métriques de perf  | `False`                    |
| `GRAPHQL_PERFORMANCE_HEADERS` | Ajoute les headers de perf    | `False`                    |

---

## Voir Aussi

- [Requêtes](./queries.md) - Utilisation des query_settings
- [Mutations](./mutations.md) - Utilisation des mutation_settings
- [Permissions](../security/permissions.md) - Utilisation des security_settings
- [Déploiement](../deployment/production.md) - Configuration production
