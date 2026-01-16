# Mutations GraphQL

## Vue d'Ensemble

Rail Django génère automatiquement les mutations CRUD pour chaque modèle Django. Ce guide couvre les mutations auto-générées, les opérations bulk, les mutations personnalisées et les relations imbriquées.

---

## Table des Matières

1. [Mutations Auto-Générées](#mutations-auto-générées)
2. [Create](#create)
3. [Update](#update)
4. [Delete](#delete)
5. [Opérations Bulk](#opérations-bulk)
6. [Relations Imbriquées](#relations-imbriquées)
7. [Mutations de Méthodes](#mutations-de-méthodes)
8. [Configuration](#configuration)

---

## Mutations Auto-Générées

Pour chaque modèle, Rail Django génère :

| Mutation    | Format                | Description                    |
| ----------- | --------------------- | ------------------------------ |
| Create      | `create_<model>`      | Crée une nouvelle instance     |
| Update      | `update_<model>`      | Modifie une instance existante |
| Delete      | `delete_<model>`      | Supprime une instance          |
| Bulk Create | `bulk_create_<model>` | Crée plusieurs instances       |
| Bulk Update | `bulk_update_<model>` | Modifie plusieurs instances    |
| Bulk Delete | `bulk_delete_<model>` | Supprime plusieurs instances   |

**Exemple pour le modèle `Product` :**

```graphql
type Mutation {
  create_product(input: ProductCreateInput!): ProductMutationPayload
  update_product(id: ID!, input: ProductUpdateInput!): ProductMutationPayload
  delete_product(id: ID!): DeletePayload
  bulk_create_product(inputs: [ProductCreateInput!]!): BulkProductPayload
  bulk_update_product(inputs: [ProductUpdateWithIdInput!]!): BulkProductPayload
  bulk_delete_product(ids: [ID!]!): BulkDeletePayload
}
```

---

## Create

### Mutation Basique

```graphql
mutation CreateProduct($input: ProductCreateInput!) {
  create_product(input: $input) {
    ok
    object {
      id
      name
      sku
      price
    }
    errors {
      field
      message
    }
  }
}
```

**Variables :**

```json
{
  "input": {
    "name": "Nouveau Produit",
    "sku": "PRD-001",
    "price": "99.99",
    "category_id": "1",
    "is_active": true
  }
}
```

### Réponse Succès

```json
{
  "data": {
    "create_product": {
      "ok": true,
      "object": {
        "id": "42",
        "name": "Nouveau Produit",
        "sku": "PRD-001",
        "price": "99.99"
      },
      "errors": null
    }
  }
}
```

### Réponse Erreur (Validation)

```json
{
  "data": {
    "create_product": {
      "ok": false,
      "object": null,
      "errors": [
        {
          "field": "sku",
          "message": "Un produit avec ce SKU existe déjà."
        },
        {
          "field": "price",
          "message": "Le prix doit être positif."
        }
      ]
    }
  }
}
```

---

## Update

### Mutation Basique

```graphql
mutation UpdateProduct($id: ID!, $input: ProductUpdateInput!) {
  update_product(id: $id, input: $input) {
    ok
    object {
      id
      name
      price
    }
    errors {
      field
      message
    }
  }
}
```

**Variables :**

```json
{
  "id": "42",
  "input": {
    "price": "89.99",
    "is_active": false
  }
}
```

### Mise à Jour Partielle

Seuls les champs fournis sont modifiés :

```json
{
  "id": "42",
  "input": {
    "price": "79.99"
  }
}
```

### Champs Read-Only

Les champs marqués `read_only` dans `GraphQLMeta` sont ignorés :

```python
class Product(models.Model):
    sku = models.CharField(max_length=50)

    class GraphQLMeta:
        fields = GraphQLMeta.Fields(
            read_only=["sku"],  # Non modifiable via update
        )
```

---

## Delete

### Mutation Basique

```graphql
mutation DeleteProduct($id: ID!) {
  delete_product(id: $id) {
    ok
    errors {
      message
    }
  }
}
```

**Variables :**

```json
{
  "id": "42"
}
```

### Réponse Succès

```json
{
  "data": {
    "delete_product": {
      "ok": true,
      "errors": null
    }
  }
}
```

### Gestion des Contraintes

Si la suppression échoue (contrainte FK) :

```json
{
  "data": {
    "delete_product": {
      "ok": false,
      "errors": [
        {
          "message": "Impossible de supprimer : cet élément est référencé par d'autres enregistrements."
        }
      ]
    }
  }
}
```

---

## Opérations Bulk

### Activation

```python
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        "generate_bulk": True,
        "enable_bulk_operations": True,
        "bulk_batch_size": 100,
    },
}
```

### Bulk Create

```graphql
mutation BulkCreateProducts($inputs: [ProductCreateInput!]!) {
  bulk_create_product(inputs: $inputs) {
    ok
    count
    objects {
      id
      name
    }
    errors {
      index
      field
      message
    }
  }
}
```

**Variables :**

```json
{
  "inputs": [
    {
      "name": "Produit A",
      "sku": "A-001",
      "price": "10.00",
      "category_id": "1"
    },
    {
      "name": "Produit B",
      "sku": "B-001",
      "price": "20.00",
      "category_id": "1"
    },
    {
      "name": "Produit C",
      "sku": "C-001",
      "price": "30.00",
      "category_id": "2"
    }
  ]
}
```

### Bulk Update

```graphql
mutation BulkUpdateProducts($inputs: [ProductUpdateWithIdInput!]!) {
  bulk_update_product(inputs: $inputs) {
    ok
    count
    objects {
      id
      price
    }
  }
}
```

**Variables :**

```json
{
  "inputs": [
    { "id": "1", "price": "15.00" },
    { "id": "2", "price": "25.00" },
    { "id": "3", "is_active": false }
  ]
}
```

### Bulk Delete

```graphql
mutation BulkDeleteProducts($ids: [ID!]!) {
  bulk_delete_product(ids: $ids) {
    ok
    count
  }
}
```

**Variables :**

```json
{
  "ids": ["1", "2", "3"]
}
```

---

## Relations Imbriquées

### Activation

```python
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        "enable_nested_relations": True,
        "nested_relations_config": {},
    },
}
```

### Create avec Relation

Créez l'objet parent et les enfants en une seule mutation :

```graphql
mutation CreateOrder($input: OrderCreateInput!) {
  create_order(input: $input) {
    ok
    object {
      id
      reference
      items {
        id
        product {
          name
        }
        quantity
      }
    }
  }
}
```

**Variables :**

```json
{
  "input": {
    "customer_id": "1",
    "items": [
      { "product_id": "10", "quantity": 2, "price": "99.99" },
      { "product_id": "15", "quantity": 1, "price": "49.99" }
    ]
  }
}
```

### Update avec Relation

```graphql
mutation UpdateOrder($id: ID!, $input: OrderUpdateInput!) {
  update_order(id: $id, input: $input) {
    ok
    object {
      id
      items {
        id
        quantity
      }
    }
  }
}
```

**Variables :**

```json
{
  "id": "42",
  "input": {
    "items": [
      { "id": "100", "quantity": 5 },
      { "product_id": "20", "quantity": 1, "price": "29.99" }
    ]
  }
}
```

Comportement :

- Élément avec `id` : mise à jour
- Élément sans `id` : création
- Éléments absents : suppression (si configuré)

### Configuration des Relations Imbriquées

```python
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        "nested_relations_config": {
            "store.Order": {
                "items": {
                    "create": True,
                    "update": True,
                    "delete": True,  # Supprimer les absents
                    "max_items": 50,
                },
            },
        },
    },
}
```

---

## Mutations de Méthodes

Exposez des méthodes de modèle comme mutations GraphQL.

### Déclaration

```python
from django.db import models

class Order(models.Model):
    status = models.CharField(max_length=20, default="draft")

    def confirm(self, confirmed_by=None):
        """
        Confirme la commande.

        Args:
            confirmed_by: Utilisateur qui confirme.

        Returns:
            L'instance mise à jour.
        """
        self.status = "confirmed"
        self.confirmed_at = timezone.now()
        self.confirmed_by = confirmed_by
        self.save()
        return self

    def cancel(self, reason):
        """
        Annule la commande.

        Args:
            reason: Motif d'annulation.
        """
        self.status = "cancelled"
        self.cancellation_reason = reason
        self.save()
        return self

    class GraphQLMeta:
        # Expose ces méthodes comme mutations
        method_mutations = ["confirm", "cancel"]
```

### Utilisation

```graphql
mutation ConfirmOrder($id: ID!) {
  confirm_order(id: $id) {
    ok
    object {
      id
      status
      confirmed_at
    }
  }
}

mutation CancelOrder($id: ID!, $reason: String!) {
  cancel_order(id: $id, reason: $reason) {
    ok
    object {
      id
      status
      cancellation_reason
    }
  }
}
```

### Configuration des Méthodes

```python
class Order(models.Model):
    class GraphQLMeta:
        method_mutations = {
            "confirm": {
                "permissions": ["store.confirm_order"],
                "description": "Confirme une commande en attente",
            },
            "cancel": {
                "permissions": ["store.cancel_order"],
                "required_args": ["reason"],
            },
        }
```

---

## Configuration

### Paramètres Globaux

```python
RAIL_DJANGO_GRAPHQL = {
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

        # ─── Relations ───
        "enable_nested_relations": True,
        "nested_relations_config": {},

        # ─── Champs Requis ───
        "required_update_fields": {},
    },
}
```

### Désactiver par Modèle

```python
class ReadOnlyModel(models.Model):
    class GraphQLMeta:
        # Désactiver toutes les mutations
        mutations = False

        # Ou sélectivement
        # mutations = {
        #     "create": True,
        #     "update": False,
        #     "delete": False,
        # }
```

### Champs Requis pour Update

```python
RAIL_DJANGO_GRAPHQL = {
    "mutation_settings": {
        "required_update_fields": {
            "store.Order": ["id"],  # Toujours requis
        },
    },
}
```

---

## Voir Aussi

- [Requêtes](./queries.md) - Lecture des données
- [Configuration](./configuration.md) - Tous les paramètres
- [Permissions](../security/permissions.md) - Contrôle d'accès aux mutations
