# Requêtes GraphQL

## Vue d'Ensemble

Rail Django génère automatiquement des requêtes GraphQL pour chaque modèle Django. Ce guide couvre les différents types de requêtes, le filtrage avancé, la pagination et le tri.

---

## Table des Matières

1. [Types de Requêtes](#types-de-requêtes)
2. [Requête Unique](#requête-unique)
3. [Requête Liste](#requête-liste)
4. [Filtrage Avancé](#filtrage-avancé)
5. [Pagination](#pagination)
6. [Tri (Ordering)](#tri-ordering)
7. [Groupement (Aggregation)](#groupement-aggregation)
8. [GraphQLMeta - Configuration](#graphqlmeta---configuration)

---

## Types de Requêtes

Pour chaque modèle, Rail Django génère :

| Champ     | Format            | Description          |
| --------- | ----------------- | -------------------- |
| Single    | `<model>`         | Un seul objet par ID |
| List      | `<model>s`        | Liste avec filtres   |
| Paginated | `<model>s_pages`  | Liste paginée        |
| Grouped   | `<model>s_groups` | Agrégation           |

**Exemple pour le modèle `Product` :**

```graphql
type Query {
  product(id: ID!): ProductType
  products(
    filters: ProductFilter
    order_by: [String]
    limit: Int
    offset: Int
  ): [ProductType]
  products_pages(
    page: Int
    per_page: Int
    filters: ProductFilter
  ): ProductPageType
  products_groups(group_by: String!, limit: Int): [GroupBucketType]
}
```

---

## Requête Unique

### Par ID

```graphql
query GetProduct($id: ID!) {
  product(id: $id) {
    id
    name
    sku
    price
    category {
      id
      name
    }
  }
}
```

### Par Autre Champ

Si configuré via `additional_lookup_fields` :

```graphql
query GetProductBySku($sku: String!) {
  product(sku: $sku) {
    id
    name
  }
}
```

Configuration :

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        "additional_lookup_fields": {
            "store.Product": ["sku", "slug"],
        },
    },
}
```

---

## Requête Liste

### Basique

```graphql
query ListProducts {
  products {
    id
    name
    price
  }
}
```

### Avec Limite

```graphql
query ListProducts {
  products(limit: 20, offset: 0) {
    id
    name
  }
}
```

### Avec Relations

```graphql
query ListProducts {
  products {
    id
    name
    category {
      name
    }
    supplier {
      company_name
      contact_email
    }
  }
}
```

---

## Filtrage Avancé

### Filtres Simples

```graphql
query FilteredProducts {
  products(
    filters: {
      is_active__exact: true
      price__gte: 100
      name__icontains: "premium"
    }
  ) {
    id
    name
    price
  }
}
```

### Opérateurs Disponibles

| Opérateur    | Description                   | Exemple                             |
| ------------ | ----------------------------- | ----------------------------------- |
| `exact`      | Égalité exacte                | `status__exact: "active"`           |
| `iexact`     | Égalité insensible à la casse | `name__iexact: "product"`           |
| `contains`   | Contient (sensible)           | `name__contains: "Pro"`             |
| `icontains`  | Contient (insensible)         | `name__icontains: "pro"`            |
| `startswith` | Commence par                  | `sku__startswith: "PRD"`            |
| `endswith`   | Finit par                     | `email__endswith: ".com"`           |
| `in`         | Dans une liste                | `status__in: ["active", "pending"]` |
| `gt`, `gte`  | Plus grand (ou égal)          | `price__gt: 100`                    |
| `lt`, `lte`  | Plus petit (ou égal)          | `price__lt: 500`                    |
| `range`      | Entre deux valeurs            | `price__range: [100, 500]`          |
| `isnull`     | Est null                      | `deleted_at__isnull: true`          |
| `date`       | Partie date                   | `created_at__date: "2026-01-16"`    |

### Filtres Complexes (AND/OR/NOT)

```graphql
query ComplexFilter {
  products(
    filters: {
      AND: [{ is_active__exact: true }, { price__gte: 50 }]
      OR: [
        { category__name__icontains: "electronics" }
        { category__name__icontains: "accessories" }
      ]
      NOT: { status__exact: "discontinued" }
    }
  ) {
    id
    name
  }
}
```

### Filtres sur Relations

```graphql
query ProductsByCategory {
  products(
    filters: {
      category__name__icontains: "Electronics"
      supplier__country__exact: "FR"
    }
  ) {
    id
    name
    category {
      name
    }
    supplier {
      country
    }
  }
}
```

### Filtres Temporels Prédéfinis

```graphql
query RecentProducts {
  products(
    filters: {
      created_at_today: true
      # Ou: created_at_this_week: true
      # Ou: created_at_past_month: true
    }
  ) {
    id
    name
    created_at
  }
}
```

---

## Pagination

### Offset Pagination (Défaut)

```graphql
query PaginatedProducts($offset: Int!, $limit: Int!) {
  products(offset: $offset, limit: $limit) {
    id
    name
  }
}
```

Variables : `{ "offset": 0, "limit": 20 }`

### Page-Based Pagination

```graphql
query PagedProducts($page: Int!, $perPage: Int!) {
  products_pages(page: $page, per_page: $perPage) {
    items {
      id
      name
    }
    page_info {
      total_count
      page_count
      current_page
      per_page
      has_next_page
      has_previous_page
    }
  }
}
```

### Configuration de Pagination

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        "generate_pagination": True,
        "enable_pagination": True,
        "default_page_size": 20,
        "max_page_size": 100,
    },
}
```

### Relay-Style (Optionnel)

```python
"query_settings": {
    "use_relay": True,
}
```

```graphql
query RelayProducts($first: Int!, $after: String) {
  products(first: $first, after: $after) {
    edges {
      cursor
      node {
        id
        name
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

---

## Tri (Ordering)

### Tri Simple

```graphql
query OrderedProducts {
  products(order_by: ["name"]) {
    id
    name
  }
}
```

### Tri Descendant

Préfixez avec `-` :

```graphql
query OrderedProducts {
  products(order_by: ["-price"]) {
    id
    name
    price
  }
}
```

### Tri Multiple

```graphql
query OrderedProducts {
  products(order_by: ["-price", "name"]) {
    id
    name
    price
  }
}
```

### Tri sur Relations

```graphql
query OrderedProducts {
  products(order_by: ["category__name", "-created_at"]) {
    id
    name
    category {
      name
    }
  }
}
```

### Configuration du Tri

```python
class Product(models.Model):
    class GraphQLMeta:
        ordering = GraphQLMeta.Ordering(
            allowed=["name", "price", "created_at", "category__name"],
            default=["-created_at"],
        )
```

---

## Groupement (Aggregation)

### Comptage par Groupe

```graphql
query ProductsByCategory {
  products_groups(group_by: "category__name", order_by: "-count", limit: 10) {
    key # Valeur du groupe
    label # Label affiché
    count # Nombre d'éléments
  }
}
```

**Résultat :**

```json
{
  "data": {
    "products_groups": [
      { "key": "Electronics", "label": "Electronics", "count": 150 },
      { "key": "Accessories", "label": "Accessories", "count": 85 },
      { "key": "Software", "label": "Software", "count": 42 }
    ]
  }
}
```

### Avec Filtres

```graphql
query ActiveProductsByCategory {
  products_groups(
    group_by: "category__name"
    filters: { is_active__exact: true }
    limit: 5
  ) {
    key
    count
  }
}
```

### Configuration

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        "max_grouping_buckets": 200,
    },
}
```

---

## GraphQLMeta - Configuration

### Structure Complète

```python
from django.db import models
from rail_django.core.meta import GraphQLMeta as GraphQLMetaConfig

class Product(models.Model):
    """
    Modèle Produit avec configuration GraphQL complète.

    Attributes:
        name: Nom du produit.
        sku: Code article unique.
        price: Prix unitaire HT.
        category: Catégorie du produit.
        is_active: Statut d'activation.
    """
    name = models.CharField("Nom", max_length=200)
    sku = models.CharField("Référence", max_length=50, unique=True)
    price = models.DecimalField("Prix", max_digits=10, decimal_places=2)
    category = models.ForeignKey("Category", on_delete=models.CASCADE)
    is_active = models.BooleanField("Actif", default=True)
    internal_notes = models.TextField("Notes internes", blank=True)

    class GraphQLMeta(GraphQLMetaConfig):
        # ─── Exposition des Champs ───
        fields = GraphQLMetaConfig.Fields(
            exclude=["internal_notes"],  # Jamais exposé
            read_only=["sku"],           # Non modifiable via mutation
        )

        # ─── Filtrage ───
        filtering = GraphQLMetaConfig.Filtering(
            # Champs pour la recherche rapide
            quick=["name", "sku"],
            # Configuration détaillée par champ
            fields={
                "name": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "icontains", "istartswith"],
                ),
                "price": GraphQLMetaConfig.FilterField(
                    lookups=["exact", "gt", "lt", "range"],
                ),
                "is_active": GraphQLMetaConfig.FilterField(
                    lookups=["exact"],
                ),
                "category__name": GraphQLMetaConfig.FilterField(
                    lookups=["icontains"],
                ),
            },
        )

        # ─── Tri ───
        ordering = GraphQLMetaConfig.Ordering(
            allowed=["name", "price", "created_at", "category__name"],
            default=["-created_at"],
        )
```

### Filtering Quick

La configuration `quick` active la recherche textuelle rapide :

```graphql
query QuickSearch {
  products(quick: "iPhone") {
    id
    name
  }
}
```

Recherche dans tous les champs `quick` avec `icontains`.

---

## Voir Aussi

- [Mutations](./mutations.md) - Opérations CRUD
- [Configuration](./configuration.md) - Paramètres query_settings
- [Permissions](../security/permissions.md) - Contrôle d'accès aux queries
