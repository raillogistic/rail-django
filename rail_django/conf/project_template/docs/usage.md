# Rail Django - Guide d'Utilisation Complet

Bienvenue dans la documentation de **Rail Django**, le framework de production pour construire des APIs GraphQL d'entreprise avec Django.

---

## 📖 Présentation

Rail Django simplifie le développement d'APIs GraphQL en automatisant la génération de schémas, les mutations CRUD, et en intégrant des fonctionnalités d'entreprise prêtes à l'emploi.

### Philosophie

1. **Convention plutôt que Configuration** - Définissez un modèle Django, obtenez une API fonctionnelle immédiatement.
2. **Sécurité par Défaut** - Permissions, limites de profondeur et validation des entrées activées par défaut.
3. **Batteries Incluses** - Audit, exports, webhooks et moniteur de santé intégrés.

---

## 📑 Table des Matières

### Démarrage Rapide

| Guide                                               | Description                             |
| --------------------------------------------------- | --------------------------------------- |
| [Installation](./getting-started/installation.md)   | Prérequis et installation du framework  |
| [Démarrage Rapide](./getting-started/quickstart.md) | Créer votre premier projet en 5 minutes |

### Sécurité

| Guide                                                | Description                                                |
| ---------------------------------------------------- | ---------------------------------------------------------- |
| [Authentification JWT](./security/authentication.md) | Connexion, tokens, cookies et sessions                     |
| [Permissions & RBAC](./security/permissions.md)      | Contrôle d'accès basé sur les rôles, permissions par champ |
| [Authentification Multi-Facteurs](./security/mfa.md) | Configuration TOTP et sécurisation des comptes             |

### Extensions

| Guide                                          | Description                                        |
| ---------------------------------------------- | -------------------------------------------------- |
| [Webhooks](./extensions/webhooks.md)           | Envoi d'événements vers des systèmes externes      |
| [Subscriptions](./extensions/subscriptions.md) | Temps réel avec GraphQL et WebSocket               |
| [Audit & Logging](./extensions/audit.md)       | Traçabilité des actions et événements de sécurité  |
| [Export de Données](./extensions/exporting.md) | Export Excel/CSV avec gardes-fous                  |
| [Reporting & BI](./extensions/reporting.md)    | Définir des datasets analytiques et visualisations |
| [Génération PDF](./extensions/templating.md)   | Templates HTML vers PDF                            |
| [Monitoring Santé](./extensions/health.md)     | Points de terminaison de santé pour orchestration  |
| [Métadonnées Schema](./extensions/metadata.md) | Introspection de schéma pour interfaces dynamiques |
| [Observabilité](./extensions/observability.md) | Sentry, OpenTelemetry et métriques Prometheus      |

### GraphQL

| Guide                                       | Description                                                |
| ------------------------------------------- | ---------------------------------------------------------- |
| [Requêtes](./graphql/queries.md)            | Listes, filtres, pagination et tri                         |
| [Mutations](./graphql/mutations.md)         | CRUD automatique, opérations bulk, méthodes personnalisées |
| [Configuration](./graphql/configuration.md) | Référence complète des paramètres                          |

### Performance

| Guide                                           | Description                                 |
| ----------------------------------------------- | ------------------------------------------- |
| [Optimisation](./performance/optimization.md)   | Prefetch, DataLoader, limites de complexité |
| [Rate Limiting](./performance/rate-limiting.md) | Limitation de débit des requêtes            |

### Déploiement

| Guide                                    | Description                                  |
| ---------------------------------------- | -------------------------------------------- |
| [Production](./deployment/production.md) | Docker, checklist, HTTPS et bonnes pratiques |

---

## 🚀 Démarrage Express

```bash
# Installation
pip install rail-django

# Création du projet
rail-admin startproject mon_projet
cd mon_projet

# Initialisation
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Accédez au playground GraphiQL : `http://localhost:8000/graphql/graphiql/`

---

## 🏗️ Structure du Projet

```
mon_projet/
├── manage.py           # Point d'entrée Django
├── root/               # Configuration principale
│   ├── settings/       # Paramètres (base, dev, prod)
│   ├── urls.py         # Routage global
│   └── asgi.py         # WebSocket support
├── apps/               # Vos applications Django
├── requirements/       # Dépendances (base, dev, prod)
└── docs/               # Cette documentation
```

---

## ⚙️ Configuration Principale

Toute la configuration est centralisée dans `RAIL_DJANGO_GRAPHQL` :

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "authentication_required": True,
        "enable_graphiql": True,
        "auto_camelcase": False,
    },
    "mutation_settings": {
        "generate_create": True,
        "generate_update": True,
        "generate_delete": True,
    },
    "security_settings": {
        "enable_field_permissions": True,
        "enable_rate_limiting": False,
    },
}
```

📖 Voir [Configuration Complète](./graphql/configuration.md) pour toutes les options.

---

## 📊 Fonctionnalités Clés

### Auto-Génération de Schéma

Définissez vos modèles Django, Rail Django génère automatiquement :

- Types GraphQL (`DjangoObjectType`)
- Filtres avancés (`FilterSet`)
- Requêtes list/retrieve
- Mutations create/update/delete

```python
# apps/store/models.py
class Product(models.Model):
    """
    Modèle Produit.

    Attributes:
        name: Nom du produit.
        price: Prix unitaire.
        is_active: Statut d'activation.
    """
    name = models.CharField("Nom", max_length=255)
    price = models.DecimalField("Prix", max_digits=10, decimal_places=2)
    is_active = models.BooleanField("Actif", default=True)
```

### Requête GraphQL Automatique

```graphql
query {
  products(is_active: true, price_Gt: 50, ordering: ["-price"]) {
    id
    name
    price
  }
}
```

### Mutations Automatiques

```graphql
mutation {
  create_product(input: { name: "Nouveau", price: 99.99 }) {
    ok
    object {
      id
      name
    }
    errors {
      field
      message
    }
  }
}
```

---

## 🔐 Sécurité Intégrée

### Authentification JWT

```graphql
mutation {
  login(username: "user", password: "secret") {
    token
    refresh_token
    user {
      id
      username
    }
  }
}
```

### Permissions par Champ

```python
class Customer(models.Model):
    email = models.EmailField()

    class GraphQLMeta:
        field_permissions = {
            "email": {
                "roles": ["support", "admin"],
                "visibility": "masked",
                "mask_value": "***@***.com"
            }
        }
```

📖 Voir [Permissions & RBAC](./security/permissions.md)

---

## 📡 Extensions Temps Réel

### Webhooks

Envoyez des événements aux systèmes externes lors de create/update/delete.

```python
RAIL_DJANGO_WEBHOOKS = {
    "enabled": True,
    "endpoints": [{
        "name": "orders",
        "url": "https://example.com/webhooks/orders",
        "include_models": ["store.Order"],
    }],
}
```

📖 Voir [Webhooks](./extensions/webhooks.md)

### Subscriptions GraphQL

```graphql
subscription {
  order_created(filters: { status: { exact: "pending" } }) {
    event
    node {
      id
      status
    }
  }
}
```

📖 Voir [Subscriptions](./extensions/subscriptions.md)

---

## 📈 Reporting & Export

### Datasets BI

```python
from rail_django.extensions.reporting import ReportingDataset

ReportingDataset.objects.create(
    code="monthly_sales",
    source_app_label="store",
    source_model="Order",
    dimensions=[{"field": "created_at", "transform": "trunc:month"}],
    metrics=[{"field": "total", "aggregation": "sum", "name": "revenue"}],
)
```

📖 Voir [Reporting & BI](./extensions/reporting.md)

### Export Excel/CSV

```bash
curl -X POST /api/v1/export/ \
  -H "Authorization: Bearer <jwt>" \
  -d '{"app_name": "store", "model_name": "Product", "file_extension": "xlsx"}'
```

📖 Voir [Export de Données](./extensions/exporting.md)

---

## 🏥 Monitoring

### Health Check

```graphql
query {
  health {
    health_status {
      overall_status
      components {
        databases {
          status
        }
      }
    }
  }
}
```

📖 Voir [Monitoring Santé](./extensions/health.md)

---

## 📚 Ressources Additionnelles

- [CHANGELOG](../CHANGELOG.md) - Historique des versions
- [CONTRIBUTING](../CONTRIBUTING.md) - Guide de contribution
- [GitHub](https://github.com/raillogistic/rail-django) - Code source

---

**Rail Django** - _Construisez plus vite, scalez mieux._
