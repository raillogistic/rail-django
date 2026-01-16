# Métadonnées de Schéma (Metadata V2)

## Vue d'Ensemble

Rail Django expose des métadonnées riches sur vos modèles Django via GraphQL. Ces métadonnées permettent aux frontends de générer automatiquement des formulaires, tableaux et vues de détail sans codage manuel.

---

## Table des Matières

1. [Activation](#activation)
2. [Queries Disponibles](#queries-disponibles)
3. [Structure ModelSchema](#structure-modelschema)
4. [Classification des Champs](#classification-des-champs)
5. [Permissions et Visibilité](#permissions-et-visibilité)
6. [Intégration Frontend](#intégration-frontend)
7. [Personnalisation via GraphQLMeta](#personnalisation-via-graphqlmeta)
8. [V1 vs V2](#v1-vs-v2)

---

## Activation

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        "show_metadata": True,  # Active metadata V1 et V2
    },
}
```

---

## Queries Disponibles

### modelSchema - Schéma Complet d'un Modèle

```graphql
query ModelSchema($app: String!, $model: String!) {
  model_schema(app: $app, model: $model) {
    app
    model
    verbose_name
    verbose_name_plural
    primary_key
    ordering

    fields { ... }
    relationships { ... }
    filters { ... }
    mutations { ... }
    permissions { ... }

    field_groups { ... }
    templates { ... }

    metadata_version
    custom_metadata
  }
}
```

### availableModelsV2 - Liste des Modèles

```graphql
query AvailableModels($app: String) {
  available_models_v2(app: $app) {
    app
    model
    verbose_name
    verbose_name_plural
  }
}
```

### appSchemas - Tous les Schémas d'une App

```graphql
query AppSchemas($app: String!) {
  app_schemas(app: $app) {
    model
    verbose_name
    fields {
      name
      field_type
    }
  }
}
```

---

## Structure ModelSchema

### Exemple Complet

```graphql
query OrderSchema {
  model_schema(app: "store", model: "Order") {
    # ─── Identification ───
    app # "store"
    model # "Order"
    verbose_name # "Commande"
    verbose_name_plural # "Commandes"
    primary_key # "id"
    ordering # ["-created_at"]
    # ─── Champs ───
    fields {
      name # "status"
      verbose_name # "Statut"
      field_type # "CharField"
      graphql_type # "String"
      required # true
      nullable # false
      editable # true
      unique # false
      max_length # 20
      # Choix (si applicable)
      choices {
        value # "pending"
        label # "En attente"
      }

      # Classification
      is_date # false
      is_datetime # false
      is_numeric # false
      is_boolean # false
      is_text # true
      is_rich_text # false
      is_file # false
      is_image # false
      is_json # false
      is_fsm_field # true
      # Transitions FSM
      fsm_transitions {
        name # "confirm"
        source # ["pending"]
        target # "confirmed"
        label # "Confirmer"
      }

      # Permissions (pour l'utilisateur actuel)
      readable # true
      writable # false
      visibility # "VISIBLE" | "MASKED" | "HIDDEN"
    }

    # ─── Relations ───
    relationships {
      name # "customer"
      related_app # "crm"
      related_model # "Customer"
      relation_type # "FOREIGN_KEY" | "MANY_TO_MANY" | "REVERSE_FK"
      is_reverse # false
      is_to_one # true
      is_to_many # false
      required # true
      readable # true
      writable # true
    }

    # ─── Filtres Disponibles ───
    filters {
      field_name # "status"
      field_label # "Statut"
      is_nested # false
      related_model # null
      options {
        name # "status__exact"
        lookup # "exact"
        help_text # "Correspondance exacte"
        choices {
          value # "pending"
          label # "En attente"
        }
      }
    }

    # ─── Mutations Disponibles ───
    mutations {
      name # "create_order"
      operation # "CREATE" | "UPDATE" | "DELETE" | "METHOD"
      allowed # true
      required_permissions # ["store.add_order"]
    }

    # ─── Permissions Modèle ───
    permissions {
      can_list # true
      can_create # true
      can_update # true
      can_delete # false
      can_export # true
    }

    # ─── Groupes de Champs ───
    field_groups {
      key # "main"
      label # "Informations principales"
      fields # ["reference", "customer", "status"]
    }

    # ─── Templates PDF ───
    templates {
      key # "download_invoice"
      title # "Facture"
      endpoint # "/api/templates/store/order/download_invoice/{pk}/"
    }

    metadata_version # "2.0"
    custom_metadata # {"icon": "shopping-cart", "color": "#4A90D9"}
  }
}
```

---

## Classification des Champs

Les champs sont classifiés avec des flags booléens pour faciliter la sélection de widgets frontend.

### Flags de Classification

| Flag           | Description                | Types Django                                 |
| -------------- | -------------------------- | -------------------------------------------- |
| `is_date`      | Champ date                 | `DateField`                                  |
| `is_datetime`  | Champ date+heure           | `DateTimeField`                              |
| `is_numeric`   | Valeur numérique           | `IntegerField`, `DecimalField`, `FloatField` |
| `is_boolean`   | Booléen                    | `BooleanField`, `NullBooleanField`           |
| `is_text`      | Texte court                | `CharField`                                  |
| `is_rich_text` | Texte long (éditeur riche) | `TextField`                                  |
| `is_file`      | Fichier uploadé            | `FileField`                                  |
| `is_image`     | Image                      | `ImageField`                                 |
| `is_json`      | Données JSON               | `JSONField`                                  |
| `is_fsm_field` | Champ django-fsm           | `FSMField`                                   |

### Transitions FSM

Pour les champs `django-fsm`, les transitions disponibles sont exposées :

```json
{
  "name": "status",
  "is_fsm_field": true,
  "fsm_transitions": [
    {
      "name": "confirm",
      "source": ["pending"],
      "target": "confirmed",
      "label": "Confirmer la commande"
    },
    {
      "name": "ship",
      "source": ["confirmed"],
      "target": "shipped",
      "label": "Expédier"
    }
  ]
}
```

---

## Permissions et Visibilité

### Champs de Permission

Chaque champ inclut les permissions de l'utilisateur **actuel** :

```json
{
  "name": "margin",
  "readable": true,
  "writable": false,
  "visibility": "MASKED"
}
```

### Niveaux de Visibilité

| Visibility | Description                                  |
| ---------- | -------------------------------------------- |
| `VISIBLE`  | Valeur complètement visible                  |
| `MASKED`   | Valeur partiellement masquée (`***@***.com`) |
| `HIDDEN`   | Champ non visible (retourne `null`)          |

### Permissions Modèle

```json
{
  "permissions": {
    "can_list": true,
    "can_create": true,
    "can_update": true,
    "can_delete": false,
    "can_export": true
  }
}
```

---

## Intégration Frontend

### Sélection de Widget

```typescript
interface FieldSchema {
  name: string;
  verbose_name: string;
  field_type: string;
  required: boolean;
  is_date: boolean;
  is_datetime: boolean;
  is_numeric: boolean;
  is_boolean: boolean;
  is_text: boolean;
  is_rich_text: boolean;
  is_fsm_field: boolean;
  choices?: { value: string; label: string }[];
  fsm_transitions?: { name: string; label: string; target: string }[];
}

function selectWidget(field: FieldSchema): string {
  // Choix → Select
  if (field.choices?.length) return "select";

  // FSM → Badge avec actions
  if (field.is_fsm_field) return "state-badge";

  // Texte riche → Éditeur WYSIWYG
  if (field.is_rich_text) return "rich-text-editor";

  // Date/Datetime → Pickers
  if (field.is_datetime) return "datetime-picker";
  if (field.is_date) return "date-picker";

  // Numérique → Input number
  if (field.is_numeric) return "number-input";

  // Booléen → Switch
  if (field.is_boolean) return "switch";

  // Défaut → Text input
  return "text-input";
}
```

### Construction de Formulaire

```typescript
interface ModelSchema {
  fields: FieldSchema[];
  field_groups?: { key: string; label: string; fields: string[] }[];
  permissions: { can_create: boolean; can_update: boolean };
}

function buildForm(schema: ModelSchema, mode: "create" | "edit") {
  const permission =
    mode === "create"
      ? schema.permissions.can_create
      : schema.permissions.can_update;

  if (!permission) {
    throw new Error("Permission denied");
  }

  // Grouper les champs
  const groups = schema.field_groups || [
    {
      key: "default",
      label: "Informations",
      fields: schema.fields.map((f) => f.name),
    },
  ];

  return groups.map((group) => ({
    label: group.label,
    fields: group.fields
      .map((fieldName) => schema.fields.find((f) => f.name === fieldName))
      .filter((field) => field && field.editable && field.writable)
      .map((field) => ({
        name: field!.name,
        label: field!.verbose_name,
        widget: selectWidget(field!),
        required: field!.required,
        choices: field!.choices,
      })),
  }));
}
```

### Construction de Tableau

```typescript
function buildTableColumns(schema: ModelSchema) {
  return schema.fields
    .filter((field) => field.readable && field.visibility !== "HIDDEN")
    .map((field) => ({
      key: field.name,
      title: field.verbose_name,
      sortable: schema.filters?.some((f) => f.field_name === field.name),
      formatter: getFormatter(field),
    }));
}

function getFormatter(field: FieldSchema) {
  if (field.is_date) return (v: string) => formatDate(v);
  if (field.is_datetime) return (v: string) => formatDateTime(v);
  if (field.is_numeric) return (v: number) => formatNumber(v);
  if (field.is_boolean) return (v: boolean) => (v ? "✓" : "✗");
  if (field.visibility === "MASKED") return () => "***";
  return (v: any) => String(v);
}
```

---

## Personnalisation via GraphQLMeta

### Groupes de Champs

```python
class Order(models.Model):
    reference = models.CharField(max_length=50)
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE)
    status = models.CharField(max_length=20)
    notes = models.TextField(blank=True)

    class GraphQLMeta:
        field_groups = [
            {
                "key": "main",
                "label": "Informations principales",
                "fields": ["reference", "customer", "status"],
            },
            {
                "key": "details",
                "label": "Détails",
                "fields": ["notes"],
            },
        ]
```

### Métadonnées Personnalisées

```python
class Order(models.Model):
    class GraphQLMeta:
        custom_metadata = {
            "icon": "shopping-cart",
            "color": "#4A90D9",
            "dashboard_priority": 1,
            "quick_actions": ["download_invoice", "send_notification"],
        }
```

### Template PDF dans Metadata

Les templates décorés avec `@model_pdf_template` sont automatiquement exposés :

```python
class Order(models.Model):
    @model_pdf_template(content="pdf/invoice.html")
    def download_invoice(self):
        return {"order": self}
```

Résultat dans `templates` :

```json
{
  "templates": [
    {
      "key": "download_invoice",
      "title": "Invoice",
      "endpoint": "/api/templates/store/order/download_invoice/{pk}/"
    }
  ]
}
```

---

## V1 vs V2

### Comparaison

| Fonctionnalité        | V1 (`model_metadata`) | V2 (`model_schema`)             |
| --------------------- | --------------------- | ------------------------------- |
| Nombre de queries     | 3 séparées            | 1 unifiée                       |
| Classification champs | Limitée               | 15+ flags booléens              |
| Transitions FSM       | ❌                    | ✅ Complet                      |
| Groupes de champs     | ❌                    | ✅ Via GraphQLMeta              |
| Métadonnées custom    | ❌                    | ✅ Pass-through                 |
| Détails relations     | Basique               | Complet (on_delete, through)    |
| Permissions champ     | Basique               | Complet (read/write/visibility) |

### Migration V1 → V2

Les deux APIs restent disponibles simultanément. Migrez progressivement :

```typescript
// V1 (déprécié)
const { data } = await client.query({
  query: MODEL_METADATA_V1,
  variables: { app: "store", model: "Order" },
});

// V2 (recommandé)
const { data } = await client.query({
  query: MODEL_SCHEMA_V2,
  variables: { app: "store", model: "Order" },
});
```

---

## Voir Aussi

- [Configuration](../graphql/configuration.md) - Paramètres show_metadata
- [Permissions](../security/permissions.md) - Contrôle d'accès aux champs
- [GraphQLMeta](../graphql/queries.md) - Configuration par modèle
