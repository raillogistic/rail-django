# Démarrage Rapide

## Vue d'Ensemble

Ce guide vous montre comment créer une API GraphQL complète en 10 minutes avec Rail Django.

---

## Objectif

Créer une API pour gérer des **Produits** et des **Catégories** avec :

- Requêtes list/retrieve avec filtres
- Mutations CRUD
- Authentification JWT
- Permissions par rôle

---

## Étape 1 : Créer l'Application

```bash
cd mon_projet
python manage.py startapp store
```

Rail Django crée l'app dans `apps/store/`.

---

## Étape 2 : Définir les Modèles

```python
# apps/store/models.py
"""
Modèles du module Store.

Ce module contient les modèles pour la gestion du catalogue produits.
"""
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig


class Category(models.Model):
    """
    Modèle Catégorie.

    Représente une catégorie de produits dans le catalogue.

    Attributes:
        name: Nom de la catégorie.
        description: Description optionnelle.
        is_active: Indique si la catégorie est active.
    """
    name = models.CharField("Nom", max_length=100)
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Active", default=True)

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"

    def __str__(self):
        return self.name

    class GraphQLMeta(GraphQLMetaConfig):
        filtering = GraphQLMetaConfig.Filtering(
            quick=["name"],
            fields={
                "name": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "icontains"],
                ),
                "is_active": GraphQLMetaConfig.FilterField(
                    lookups=["exact"],
                ),
            },
        )
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "id"],
            default=["name"],
        )


class Product(models.Model):
    """
    Modèle Produit.

    Représente un produit dans le catalogue.

    Attributes:
        name: Nom du produit.
        sku: Code article unique.
        price: Prix unitaire HT.
        category: Catégorie du produit.
        is_active: Indique si le produit est actif.
        created_at: Date de création.
    """
    name = models.CharField("Nom", max_length=200)
    sku = models.CharField("Référence", max_length=50, unique=True)
    price = models.DecimalField("Prix", max_digits=10, decimal_places=2)
    description = models.TextField("Description", blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name="Catégorie"
    )
    is_active = models.BooleanField("Actif", default=True)
    created_at = models.DateTimeField("Créé le", auto_now_add=True)

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.sku} - {self.name}"

    class GraphQLMeta(GraphQLMetaConfig):
        # Champs
        fields = GraphQLMetaConfig.Fields(
            read_only=["sku", "created_at"],
        )

        # Filtrage
        filtering = GraphQLMetaConfig.Filtering(
            quick=["name", "sku"],
            fields={
                "name": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "icontains", "istartswith"],
                ),
                "sku": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "istartswith"],
                ),
                "price": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "gt", "lt", "range"],
                ),
                "category": GraphQLMetaConfig.FilterField(
                    lookups=["exact"],
                ),
                "is_active": GraphQLMetaConfig.FilterField(
                    lookups=["exact"],
                ),
            },
        )

        # Tri
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "price", "created_at", "category__name"],
            default=["-created_at"],
        )
```

---

## Étape 3 : Enregistrer l'Application

```python
# root/settings/base.py
INSTALLED_APPS = [
    # ...
    "apps.store",
]
```

---

## Étape 4 : Appliquer les Migrations

```bash
python manage.py makemigrations store
python manage.py migrate
```

---

## Étape 5 : Tester l'API

Démarrez le serveur :

```bash
python manage.py runserver
```

Ouvrez GraphiQL : http://localhost:8000/graphql/graphiql/

### Authentification

```graphql
mutation {
  login(username: "admin", password: "votre_password") {
    ok
    token
    user {
      username
    }
  }
}
```

Copiez le `token` et ajoutez-le dans les HTTP Headers :

```json
{
  "Authorization": "Bearer <votre_token>"
}
```

### Créer une Catégorie

```graphql
mutation {
  create_category(
    input: {
      name: "Électronique"
      description: "Appareils électroniques"
      is_active: true
    }
  ) {
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

### Créer un Produit

```graphql
mutation {
  create_product(
    input: {
      name: "iPhone 15 Pro"
      sku: "IPHONE-15-PRO"
      price: "1199.00"
      description: "Smartphone Apple dernière génération"
      category_id: "1"
      is_active: true
    }
  ) {
    ok
    object {
      id
      name
      sku
      price
      category {
        name
      }
    }
  }
}
```

### Lister les Produits

```graphql
query {
  products(
    filters: { is_active__exact: true }
    order_by: ["-price"]
    limit: 10
  ) {
    id
    name
    sku
    price
    category {
      name
    }
  }
}
```

### Filtrage Avancé

```graphql
query {
  products(
    filters: {
      price__gte: 100
      price__lte: 500
      category__name__icontains: "électronique"
    }
  ) {
    id
    name
    price
  }
}
```

### Recherche Rapide

```graphql
query {
  products(quick: "iPhone") {
    id
    name
    sku
  }
}
```

### Requête Paginée

```graphql
query {
  products_pages(page: 1, per_page: 20) {
    items {
      id
      name
      price
    }
    page_info {
      total_count
      page_count
      current_page
      has_next_page
    }
  }
}
```

---

## Étape 6 : Ajouter des Permissions

Modifier `GraphQLMeta` pour ajouter des restrictions :

```python
class Product(models.Model):
    # ... champs ...

    class GraphQLMeta(GraphQLMetaConfig):
        # ... filtering, ordering ...

        # Permissions par opération
        access = GraphQLMetaConfig.Access(
            operations={
                "list": {"roles": ["*"]},  # Tout le monde
                "retrieve": {"roles": ["*"]},
                "create": {"roles": ["catalog_manager", "admin"]},
                "update": {"roles": ["catalog_manager", "admin"]},
                "delete": {"roles": ["admin"]},
            }
        )
```

---

## Récapitulatif

Vous avez créé :

✅ Deux modèles avec relations  
✅ Requêtes auto-générées avec filtres et pagination  
✅ Mutations CRUD  
✅ Authentification JWT  
✅ Configuration des permissions

---

## Prochaines Étapes

- [Requêtes](../graphql/queries.md) - Filtrage avancé et pagination
- [Mutations](../graphql/mutations.md) - Opérations bulk et relations imbriquées
- [Permissions](../security/permissions.md) - RBAC et permissions par champ
- [Webhooks](../extensions/webhooks.md) - Notifications externes

---

## Code Complet

Le code complet de ce tutoriel est disponible dans `apps/store/` après création avec `python manage.py startapp store`.
