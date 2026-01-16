# Permissions & RBAC

## Vue d'Ensemble

Rail Django offre un système de permissions granulaire combinant le RBAC (Role-Based Access Control), les permissions au niveau des champs, et un moteur de politiques d'accès. Ce guide couvre la configuration et l'utilisation complète de ces fonctionnalités.

---

## Table des Matières

1. [Concepts de Base](#concepts-de-base)
2. [Configuration](#configuration)
3. [Contrôle d'Accès Basé sur les Rôles (RBAC)](#contrôle-daccès-basé-sur-les-rôles-rbac)
4. [Permissions par Champ](#permissions-par-champ)
5. [Moteur de Politiques](#moteur-de-politiques)
6. [GraphQLMeta - Configuration par Modèle](#graphqlmeta---configuration-par-modèle)
7. [Définition des Rôles via meta.json](#définition-des-rôles-via-metajson)
8. [API GraphQL](#api-graphql)
9. [Exemples Complets](#exemples-complets)
10. [Bonnes Pratiques](#bonnes-pratiques)

---

## Concepts de Base

### Hiérarchie des Permissions

```
Niveau                 Description
─────────────────────────────────────────────────────────
Opération             create, read, update, delete (CRUD)
Modèle                Accès au Type GraphQL entier
Champ                 Accès/visibilité par champ
Objet                 Accès contextuel (propriétaire, assigné)
```

### Types de Visibilité

| Valeur     | Comportement                                |
| ---------- | ------------------------------------------- |
| `visible`  | Champ accessible normalement                |
| `masked`   | Valeur partiellement cachée (`***@***.com`) |
| `hidden`   | Champ non visible (null ou erreur)          |
| `redacted` | Champ visible mais contenu remplacé         |

---

## Configuration

### Paramètres Globaux

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        # Active les vérifications d'authentification
        "enable_authentication": True,
        # Active les vérifications d'autorisation
        "enable_authorization": True,
        # Active le moteur de politiques allow/deny
        "enable_policy_engine": True,
        # Cache les résultats de permissions
        "enable_permission_cache": True,
        "permission_cache_ttl_seconds": 300,
        # Audit des vérifications de permissions
        "enable_permission_audit": False,
        "permission_audit_log_denies": True,
        # Permissions au niveau des champs
        "enable_field_permissions": True,
        # Mode de gestion des inputs non autorisés
        "field_permission_input_mode": "reject",  # ou "strip"
        # Permissions au niveau des objets
        "enable_object_permissions": True,
    },
    "query_settings": {
        # Requiert les permissions Django pour les queries
        "require_model_permissions": True,
        "model_permission_codename": "view",
    },
    "mutation_settings": {
        # Requiert les permissions Django pour les mutations
        "require_model_permissions": True,
        "model_permission_codenames": {
            "create": "add",
            "update": "change",
            "delete": "delete",
        },
    },
    "middleware_settings": {
        # Middleware de permissions par champ
        "enable_field_permission_middleware": True,
    },
}
```

---

## Contrôle d'Accès Basé sur les Rôles (RBAC)

### Définition des Rôles en Code

```python
from rail_django.security import role_manager, RoleDefinition

# Définir un rôle simple
role_manager.register_role(
    RoleDefinition(
        name="catalog_viewer",
        description="Accès en lecture seule au catalogue",
        permissions=[
            "store.view_product",
            "store.view_category",
        ],
    )
)

# Définir un rôle avec héritage
role_manager.register_role(
    RoleDefinition(
        name="catalog_editor",
        description="Création et modification du catalogue",
        permissions=[
            "store.add_product",
            "store.change_product",
        ],
        parent_roles=["catalog_viewer"],  # Hérite des permissions
    )
)

# Rôle système avec limites
role_manager.register_role(
    RoleDefinition(
        name="catalog_admin",
        description="Administration complète du catalogue",
        permissions=["store.*"],  # Wildcard
        parent_roles=["catalog_editor"],
        is_system_role=True,
        max_users=5,  # Limite le nombre d'utilisateurs
    )
)
```

### Décorateur @require_role

Protège les resolvers et fonctions avec des vérifications de rôle :

```python
from rail_django.security import require_role

@require_role("manager")
def resolve_financial_report(root, info):
    """
    Génère un rapport financier.
    Accessible uniquement aux managers.
    """
    return generate_report()

@require_role(["admin", "support"])  # OU logique
def resolve_sensitive_data(root, info):
    """Accessible aux admins OU support."""
    return get_sensitive_data()
```

### Permissions Contextuelles

Pour les permissions basées sur l'objet (`*_own`, `*_assigned`) :

```python
from rail_django.security import PermissionContext, role_manager

def resolve_update_project(root, info, project_id, input):
    project = Project.objects.get(pk=project_id)

    # Créer un contexte avec l'instance
    context = PermissionContext(
        user=info.context.user,
        object_instance=project
    )

    # Vérifier la permission contextuelle
    if not role_manager.has_permission(
        info.context.user,
        "project.update_own",
        context
    ):
        raise PermissionError("Vous ne pouvez modifier que vos propres projets")

    # ... logique de mise à jour
```

---

## Permissions par Champ

### Configuration dans GraphQLMeta

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Customer(models.Model):
    """
    Modèle Client avec permissions par champ.

    Attributes:
        name: Nom du client.
        email: Email (masqué pour non-support).
        phone: Téléphone (caché pour utilisateurs basiques).
        internal_notes: Notes internes (admin uniquement).
    """
    name = models.CharField("Nom", max_length=200)
    email = models.EmailField("Email")
    phone = models.CharField("Téléphone", max_length=20)
    internal_notes = models.TextField("Notes internes", blank=True)

    class GraphQLMeta(GraphQLMetaConfig):
        field_permissions = {
            "email": {
                "roles": ["support", "admin"],
                "visibility": "masked",
                "mask_value": "***@***.com",
                "access": "read",  # read, write, ou both
            },
            "phone": {
                "roles": ["support", "admin"],
                "visibility": "hidden",  # Retourne null
            },
            "internal_notes": {
                "roles": ["admin"],
                "visibility": "hidden",
                "access": "both",  # Lecture et écriture
            },
        }
```

### Comportement par Rôle

| Champ            | Utilisateur Basique | Support    | Admin      |
| ---------------- | ------------------- | ---------- | ---------- |
| `name`           | ✅ Visible          | ✅ Visible | ✅ Visible |
| `email`          | `***@***.com`       | ✅ Visible | ✅ Visible |
| `phone`          | `null`              | ✅ Visible | ✅ Visible |
| `internal_notes` | `null`              | `null`     | ✅ Visible |

### Mode de Gestion des Inputs

Contrôle le comportement lors de tentatives d'écriture sur des champs non autorisés :

```python
"security_settings": {
    # "reject" : Refuse la mutation avec une erreur
    # "strip" : Ignore silencieusement les champs non autorisés
    "field_permission_input_mode": "reject",
}
```

---

## Moteur de Politiques

Le moteur de politiques permet de définir des règles d'accès explicites avec priorités.

### Création de Politiques

```python
from rail_django.security import (
    AccessPolicy, PolicyEffect, policy_manager
)

# Politique DENY avec haute priorité
policy_manager.register_policy(
    AccessPolicy(
        name="deny_tokens_for_contractors",
        effect=PolicyEffect.DENY,
        priority=50,  # Plus haut = plus prioritaire
        roles=["contractor"],
        fields=["*token*", "*secret*"],  # Pattern matching
        operations=["read", "write"],
        reason="Les contractuels ne peuvent pas accéder aux tokens",
    )
)

# Politique ALLOW spécifique
policy_manager.register_policy(
    AccessPolicy(
        name="allow_own_profile",
        effect=PolicyEffect.ALLOW,
        priority=40,
        roles=["*"],  # Tous les rôles
        models=["auth.User"],
        operations=["read", "update"],
        conditions={"owner_field": "id"},  # Vérifie si c'est son propre profil
    )
)
```

### Résolution des Conflits

1. Les politiques sont triées par priorité (décroissante).
2. À priorité égale, **DENY l'emporte sur ALLOW**.
3. Première politique matchante détermine le résultat.

### Query Explain Permission

Debugez les décisions de permissions via GraphQL :

```graphql
query ExplainPermission {
  explain_permission(
    permission: "project.update_own"
    model_name: "store.Product"
    object_id: "123"
  ) {
    allowed
    reason
    policy_decision {
      name
      effect
      priority
      reason
    }
  }
}
```

**Réponse :**

```json
{
  "data": {
    "explain_permission": {
      "allowed": true,
      "reason": "Autorisé par politique 'allow_own_profile'",
      "policy_decision": {
        "name": "allow_own_profile",
        "effect": "ALLOW",
        "priority": 40,
        "reason": "L'utilisateur est propriétaire de l'objet"
      }
    }
  }
}
```

---

## GraphQLMeta - Configuration par Modèle

### Structure Complète

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Order(models.Model):
    """
    Modèle Commande avec configuration GraphQL complète.
    """
    reference = models.CharField("Référence", max_length=50)
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE)
    status = models.CharField("Statut", max_length=20)
    total = models.DecimalField("Total", max_digits=10, decimal_places=2)
    internal_notes = models.TextField("Notes internes", blank=True)

    class GraphQLMeta(GraphQLMetaConfig):
        # ─── Configuration des Champs ───
        fields = GraphQLMetaConfig.Fields(
            exclude=["internal_notes"],  # Jamais exposé
            read_only=["reference", "created_at"],  # Non modifiable
        )

        # ─── Filtrage ───
        filtering = GraphQLMetaConfig.Filtering(
            quick=["reference", "customer__name"],  # Recherche rapide
            fields={
                "status": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "in"],
                    choices=["draft", "pending", "completed"],
                ),
                "total": GraphQLMetaConfig.FilterField(
                    lookups=["gt", "lt", "range"],
                ),
                "created_at": GraphQLMetaConfig.FilterField(
                    lookups=["gte", "lte", "date"],
                ),
            },
        )

        # ─── Tri ───
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["reference", "total", "created_at"],
            default=["-created_at"],
        )

        # ─── Permissions par Opération ───
        access = GraphQLMetaConfig.Access(
            operations={
                "list": {"roles": ["sales", "admin"]},
                "retrieve": {"roles": ["sales", "admin"]},
                "create": {"roles": ["sales", "admin"]},
                "update": {"roles": ["admin"]},
                "delete": {"roles": ["admin"]},
            }
        )

        # ─── Permissions par Champ ───
        field_permissions = {
            "total": {
                "roles": ["accounting", "admin"],
                "visibility": "visible",
                "access": "read",
            },
        }

        # ─── Classifications (GDPR, PII) ───
        classifications = GraphQLMetaConfig.Classification(
            model=["financial"],
            fields={
                "total": ["financial", "sensitive"],
            },
        )
```

---

## Définition des Rôles via meta.json

Définissez les rôles et configurations GraphQL par application dans un fichier JSON :

### Structure du Fichier

```json
// apps/store/meta.json
{
  "roles": {
    "catalog_viewer": {
      "description": "Accès en lecture seule au catalogue.",
      "role_type": "functional",
      "permissions": ["store.view_product", "store.view_category"]
    },
    "catalog_editor": {
      "description": "Création et modification du catalogue.",
      "role_type": "business",
      "permissions": [
        "store.view_product",
        "store.add_product",
        "store.change_product"
      ],
      "parent_roles": ["catalog_viewer"]
    },
    "catalog_admin": {
      "description": "Administration complète du catalogue.",
      "role_type": "system",
      "permissions": ["store.*"],
      "parent_roles": ["catalog_editor"],
      "is_system_role": true,
      "max_users": 5
    }
  },
  "models": {
    "Product": {
      "fields": {
        "exclude": ["internal_notes"],
        "read_only": ["sku"]
      },
      "filtering": {
        "quick": ["name", "category__name"],
        "fields": {
          "status": {
            "lookups": ["exact", "in"],
            "choices": ["draft", "active"]
          },
          "price": ["gt", "lt", "range"]
        }
      },
      "ordering": {
        "allowed": ["name", "price", "created_at"],
        "default": ["-created_at"]
      },
      "access": {
        "operations": {
          "list": { "roles": ["catalog_viewer"] },
          "update": { "roles": ["catalog_admin"] }
        },
        "fields": [
          {
            "field": "cost_price",
            "access": "read",
            "visibility": "hidden",
            "roles": ["catalog_admin"]
          }
        ]
      }
    }
  }
}
```

### Notes Importantes

- Placez le fichier à la racine de l'application (`apps/store/meta.json`).
- Le loader s'exécute au démarrage ; redémarrez le serveur pour appliquer les changements.
- Les rôles sont additifs et ne remplacent pas les rôles système.
- Si un modèle définit `GraphQLMeta` en code, il a priorité sur le JSON.

---

## API GraphQL

### Mes Permissions

```graphql
query MyPermissions {
  my_permissions {
    permissions # Liste des permissions Django
    roles # Liste des rôles assignés
    is_superuser
    is_staff
  }
}
```

### Vérifier une Permission

```graphql
query CheckPermission {
  has_permission(permission: "store.change_product", object_id: "123") {
    allowed
    reason
  }
}
```

---

## Exemples Complets

### Système de Gestion de Contenu

```python
class Article(models.Model):
    """
    Modèle Article avec workflow de publication.
    """
    title = models.CharField("Titre", max_length=200)
    content = models.TextField("Contenu")
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField("Statut", max_length=20, default="draft")

    class GraphQLMeta:
        # Seuls les auteurs et éditeurs peuvent voir les brouillons
        access = {
            "operations": {
                "list": {
                    "roles": ["*"],  # Tout le monde
                    "conditions": [
                        # Ajoute automatiquement un filtre
                        {"or": [
                            {"status": "published"},
                            {"author": "current_user"},
                        ]}
                    ],
                },
                "update": {
                    "roles": ["editor"],
                    # OU l'auteur peut modifier ses propres articles
                    "object_permission": "author",
                },
            },
        }

        field_permissions = {
            "content": {
                "roles": ["editor", "author"],
                "visibility": "hidden",
                "access": "write",
            },
        }
```

### API Multi-Tenant

```python
class Project(TenantMixin, models.Model):
    """
    Projet avec isolation par tenant.
    """
    name = models.CharField("Nom", max_length=100)
    budget = models.DecimalField("Budget", max_digits=12, decimal_places=2)

    class GraphQLMeta:
        # Le tenant field est filtré automatiquement
        tenant_field = "organization"

        # Permissions additionnelles par rôle dans le tenant
        access = {
            "operations": {
                "update": {"roles": ["project_manager", "org_admin"]},
            },
        }

        field_permissions = {
            "budget": {
                "roles": ["finance", "org_admin"],
                "visibility": "masked",
                "mask_value": "****",
            },
        }
```

---

## Bonnes Pratiques

### 1. Principe du Moindre Privilège

```python
# ✅ Définissez des rôles granulaires
RoleDefinition(
    name="order_viewer",
    permissions=["store.view_order"],
)

RoleDefinition(
    name="order_processor",
    permissions=["store.view_order", "store.change_order"],
    parent_roles=["order_viewer"],
)

# ❌ Évitez les rôles trop larges
RoleDefinition(
    name="super_user",
    permissions=["*"],  # Dangereux
)
```

### 2. Audit des Permissions

```python
RAIL_DJANGO_GRAPHQL = {
    "security_settings": {
        "enable_permission_audit": True,
        "permission_audit_log_denies": True,
        "permission_audit_log_all": False,  # True en dev uniquement
    },
}
```

### 3. Tests de Permissions

```python
from django.test import TestCase
from rail_django.security import role_manager

class PermissionTests(TestCase):
    def test_catalog_viewer_cannot_edit(self):
        user = User.objects.create_user("test")
        role_manager.assign_role(user, "catalog_viewer")

        self.assertTrue(
            role_manager.has_permission(user, "store.view_product")
        )
        self.assertFalse(
            role_manager.has_permission(user, "store.change_product")
        )
```

### 4. Documentation des Rôles

Documentez clairement les rôles et leurs permissions dans votre `meta.json` :

```json
{
  "roles": {
    "support_level_1": {
      "description": "Support niveau 1: Lecture des tickets et clients.",
      "role_type": "functional",
      "permissions": ["support.view_ticket", "crm.view_customer"]
    }
  }
}
```

---

## Voir Aussi

- [Authentification JWT](./authentication.md)
- [Authentification Multi-Facteurs](./mfa.md)
- [Audit & Logging](../extensions/audit.md)
- [Configuration Complète](../graphql/configuration.md)
