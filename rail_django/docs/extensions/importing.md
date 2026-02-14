# Importation de données (Data Importing)

## Présentation

L'extension d'importation de données (`rail_django.extensions.importing`) fournit un pipeline robuste pour importer des données massivement dans les modèles Django via des fichiers CSV ou Excel (XLSX). Elle est conçue pour fonctionner de manière transparente avec `ModelTable` côté frontend.

Le processus suit un cycle de vie par étapes (Staging) permettant la validation, la correction manuelle et la simulation avant l'engagement final en base de données.

## Cycle de vie d'un import (Import Lifecycle)

Un import se déroule en cinq étapes principales :

1.  **Récupération du template** (`modelImportTemplate`) : Le client récupère la structure attendue (colonnes, types, contraintes).
2.  **Téléchargement et Staging** (`createModelImportBatch`) : Le fichier est téléchargé, parsé et les lignes sont stockées dans une table temporaire (`ImportRow`).
3.  **Révision et Correction** (`updateModelImportBatch` avec `PATCH_ROWS`) : Le client peut corriger les erreurs de validation directement sur les lignes stockées.
4.  **Validation et Simulation** (`VALIDATE` et `SIMULATE`) : Le système vérifie les doublons et simule l'insertion/mise à jour pour détecter les erreurs potentielles.
5.  **Engagement (Commit)** (`COMMIT`) : Les données sont appliquées atomiquement au modèle cible.

## Configuration

L'extension est activée par défaut si elle est présente dans les `INSTALLED_APPS`. Vous pouvez configurer les limites globales :

```python
# settings.py
RAIL_DJANGO_IMPORT = {
    "max_rows": 10000,
    "max_file_size_bytes": 26214400, # 25 MB
}
```

### Personnalisation par modèle

Utilisez `GraphQLMeta` (ou une configuration Excel associée) pour définir les clés de correspondance (Matching Keys) :

```python
class Product(models.Model):
    sku = models.CharField(max_length=50, unique=True)
    # ...

    class GraphQLMeta:
        import_config = {
            "matching_key_fields": ["sku"],
            "max_rows": 5000,
        }
```

## API GraphQL

### Requêtes (Queries)

#### modelImportTemplate
Récupère les métadonnées du template pour un modèle spécifique.

```graphql
query {
  modelImportTemplate(appLabel: "store", modelName: "Product") {
    templateId
    version
    requiredColumns { name dataType required }
    optionalColumns { name dataType required }
    maxRows
    downloadUrl
  }
}
```

#### modelImportBatch
Récupère l'état actuel d'un lot d'importation.

```graphql
query {
  modelImportBatch(batchId: "UUID") {
    status
    totalRows
    invalidRows
    rows(page: 1, perPage: 10) {
      rowNumber
      editedValues
      status
      issueCount
    }
  }
}
```

### Mutations

#### createModelImportBatch
Initialise un import en téléchargeant un fichier.

```graphql
mutation CreateImport($file: Upload!) {
  createModelImportBatch(input: {
    appLabel: "store"
    modelName: "Product"
    templateId: "store.Product"
    templateVersion: "v1"
    file: $file
    fileFormat: XLSX
  }) {
    ok
    batch { id status }
    issues { code message rowNumber }
  }
}
```

#### updateModelImportBatch
Effectue une action sur le lot (PATCH_ROWS, VALIDATE, SIMULATE, COMMIT).

```graphql
mutation {
  updateModelImportBatch(input: {
    batchId: "UUID"
    action: COMMIT
  }) {
    ok
    commitSummary {
      committedRows
      createRows
      updateRows
    }
  }
}
```

## Statuts de lot (Batch Status)

| Statut | Description |
| :--- | :--- |
| `UPLOADED` | Fichier reçu, en attente de traitement. |
| `PARSED` | Fichier lu, lignes extraites. |
| `REVIEWING` | En cours de correction manuelle. |
| `VALIDATED` | Validation des données terminée (sans erreurs bloquantes). |
| `SIMULATED` | Simulation d'écriture réussie. |
| `COMMITTED` | Données importées avec succès dans la base de données. |
| `FAILED` | Échec critique du processus. |

## Sécurité

- **Permissions** : L'utilisateur doit avoir les permissions Django `add` ou `change` sur le modèle cible.
- **Validation** : Nettoyage automatique des entrées (XSS, SQLi).
- **Atomicité** : Le commit final s'exécute dans une transaction atomique. En cas d'erreur sur une seule ligne, l'import complet est annulé.

## Voir aussi

- [Modèles & Schéma](../core/models-and-schema.md)
- [Exportation de données](./exporting.md)
- [Permissions & RBAC](../security/permissions.md)
