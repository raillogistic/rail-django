# Export de Données (Excel/CSV)

## Vue d'Ensemble

Rail Django fournit un système d'export de données sécurisé avec allowlists, limites de lignes, et support asynchrone pour les gros volumes. Les exports sont disponibles aux formats CSV et Excel (XLSX).

---

## Table des Matières

1. [Configuration](#configuration)
2. [Endpoint REST](#endpoint-rest)
3. [Options d'Export](#options-dexport)
4. [Sécurité et Allowlists](#sécurité-et-allowlists)
5. [Exports Asynchrones](#exports-asynchrones)
6. [Templates d'Export](#templates-dexport)
7. [Exemples](#exemples)
8. [Bonnes Pratiques](#bonnes-pratiques)

---

## Configuration

### Paramètres d'Export

```python
# root/settings/base.py
RAIL_DJANGO_EXPORT = {
    # ─── Limites ───
    "max_rows": 10000,          # Limite par défaut
    "max_rows_csv": 50000,      # Limite plus élevée pour CSV
    "max_rows_xlsx": 10000,     # Excel limité (mémoire)

    # ─── Streaming ───
    "enforce_streaming_csv": True,  # Stream les gros CSV
    "streaming_threshold": 1000,    # Seuil pour activer le streaming

    # ─── Formats ───
    "allowed_formats": ["csv", "xlsx"],
    "default_format": "xlsx",

    # ─── Allowlists (Sécurité) ───
    "allowed_models": [],  # Vide = tous les modèles autorisés
    "allowed_fields": {},  # {"app.Model": ["field1", "field2"]}
    "allowed_filters": {}, # {"app.Model": ["status", "created_at"]}
    "allowed_orderings": {},

    # ─── Rate Limiting ───
    "rate_limit_per_minute": 10,
    "rate_limit_per_hour": 100,

    # ─── Async ───
    "async_enabled": False,
    "async_threshold": 5000,  # Lignes au-delà desquelles passer en async
}
```

---

## Endpoint REST

### URL

```
POST /api/v1/export/
```

### Authentification

L'endpoint requiert un JWT valide :

```http
POST /api/v1/export/ HTTP/1.1
Host: api.example.com
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

### Payload Basique

```json
{
  "app_name": "store",
  "model_name": "Product",
  "file_extension": "xlsx"
}
```

### Payload Complet

```json
{
  "app_name": "store",
  "model_name": "Product",
  "file_extension": "xlsx",
  "filename": "export_produits_2026",
  "fields": [
    "id",
    "name",
    "sku",
    "category.name",
    { "accessor": "price", "title": "Prix unitaire" },
    { "accessor": "stock_quantity", "title": "Quantité en stock" }
  ],
  "ordering": ["-created_at", "name"],
  "max_rows": 5000,
  "variables": {
    "is_active__exact": true,
    "category__id__in": [1, 2, 3]
  },
  "include_headers": true,
  "date_format": "%d/%m/%Y",
  "datetime_format": "%d/%m/%Y %H:%M"
}
```

### Réponse

**Export Synchrone :**

Retourne directement le fichier binaire :

```http
HTTP/1.1 200 OK
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="export_produits_2026.xlsx"

[binary data]
```

**Export Asynchrone :**

Voir [Exports Asynchrones](#exports-asynchrones).

---

## Options d'Export

### Sélection des Champs

#### Liste Simple

```json
{
  "fields": ["id", "name", "price", "created_at"]
}
```

#### Champs Relationnels (Dot Notation)

```json
{
  "fields": [
    "id",
    "name",
    "category.name",
    "category.parent.name",
    "supplier.company_name"
  ]
}
```

#### Titres Personnalisés

```json
{
  "fields": [
    { "accessor": "id", "title": "ID Produit" },
    { "accessor": "name", "title": "Désignation" },
    { "accessor": "price", "title": "Prix HT (€)" },
    { "accessor": "category.name", "title": "Catégorie" }
  ]
}
```

### Filtrage

Les filtres utilisent la syntaxe Django ORM :

```json
{
  "variables": {
    "is_active__exact": true,
    "price__gte": 100,
    "price__lte": 500,
    "name__icontains": "premium",
    "category__id__in": [1, 2, 3],
    "created_at__gte": "2026-01-01"
  }
}
```

### Tri

```json
{
  "ordering": ["-created_at", "category__name", "name"]
}
```

### Formatage des Dates

```json
{
  "date_format": "%d/%m/%Y",
  "datetime_format": "%d/%m/%Y %H:%M:%S"
}
```

| Format           | Exemple          |
| ---------------- | ---------------- |
| `%Y-%m-%d`       | 2026-01-16       |
| `%d/%m/%Y`       | 16/01/2026       |
| `%d/%m/%Y %H:%M` | 16/01/2026 10:30 |

---

## Sécurité et Allowlists

### Principle de Défaut-Refus

Par défaut, tous les champs et filtres sont **refusés** sauf ceux explicitement autorisés.

### Configuration des Allowlists

```python
RAIL_DJANGO_EXPORT = {
    # Modèles autorisés à l'export
    "allowed_models": [
        "store.Product",
        "store.Order",
        "crm.Customer",
    ],

    # Champs autorisés par modèle
    "allowed_fields": {
        "store.Product": [
            "id", "name", "sku", "price", "category.name"
        ],
        "store.Order": [
            "id", "reference", "status", "total", "customer.name"
        ],
        "crm.Customer": [
            "id", "name", "email", "company"
            # ❌ "internal_score" non inclus = non exportable
        ],
    },

    # Filtres autorisés par modèle
    "allowed_filters": {
        "store.Product": ["is_active", "category__id", "price"],
        "store.Order": ["status", "created_at", "customer__id"],
    },

    # Colonnes de tri autorisées
    "allowed_orderings": {
        "store.Product": ["name", "price", "created_at"],
        "store.Order": ["reference", "created_at", "total"],
    },
}
```

### Validation des Requêtes

Si un champ ou filtre non autorisé est demandé :

```json
{
  "error": "Field 'internal_notes' is not allowed for export on model 'Store.Product'",
  "code": "EXPORT_FIELD_NOT_ALLOWED"
}
```

---

## Exports Asynchrones

Pour les gros volumes, utilisez les exports asynchrones.

### Activation

```python
RAIL_DJANGO_EXPORT = {
    "async_enabled": True,
    "async_threshold": 5000,  # Auto-async si > 5000 lignes
    "async_storage": "default",  # Ou "s3", "gcs"
    "async_expiry_hours": 24,
}
```

### Requête Asynchrone

```json
{
  "app_name": "store",
  "model_name": "Order",
  "file_extension": "csv",
  "async": true,
  "variables": {
    "created_at__gte": "2025-01-01"
  }
}
```

### Réponse

```json
{
  "job_id": "exp_a1b2c3d4",
  "status": "pending",
  "status_url": "/api/v1/export/jobs/exp_a1b2c3d4/",
  "download_url": "/api/v1/export/jobs/exp_a1b2c3d4/download/"
}
```

### Vérification du Statut

```http
GET /api/v1/export/jobs/exp_a1b2c3d4/
Authorization: Bearer <jwt>
```

```json
{
  "job_id": "exp_a1b2c3d4",
  "status": "completed",
  "progress": 100,
  "row_count": 15000,
  "file_size": 2456789,
  "created_at": "2026-01-16T10:30:00Z",
  "completed_at": "2026-01-16T10:32:15Z",
  "expires_at": "2026-01-17T10:30:00Z"
}
```

### Téléchargement

```http
GET /api/v1/export/jobs/exp_a1b2c3d4/download/
Authorization: Bearer <jwt>
```

---

## Templates d'Export

Définissez des templates réutilisables pour simplifier les exports fréquents.

### Création d'un Template

```python
# root/export_templates.py
EXPORT_TEMPLATES = {
    "recent_orders": {
        "app_name": "store",
        "model_name": "Order",
        "file_extension": "xlsx",
        "fields": [
            {"accessor": "reference", "title": "Réf. Commande"},
            {"accessor": "customer.name", "title": "Client"},
            {"accessor": "status", "title": "Statut"},
            {"accessor": "total", "title": "Total TTC"},
            {"accessor": "created_at", "title": "Date"},
        ],
        "ordering": ["-created_at"],
        "max_rows": 1000,
        "default_filters": {
            "created_at__gte": "last_30_days",
        },
    },
    "active_products": {
        "app_name": "store",
        "model_name": "Product",
        "fields": ["sku", "name", "price", "stock"],
        "default_filters": {
            "is_active__exact": True,
        },
    },
}
```

### Utilisation d'un Template

```json
{
  "template": "recent_orders",
  "variables": {
    "status__exact": "completed"
  }
}
```

Le template est mergé avec les variables fournies.

---

## Exemples

### Export Produits avec cURL

```bash
curl -X POST "https://api.example.com/api/v1/export/" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "store",
    "model_name": "Product",
    "file_extension": "xlsx",
    "filename": "catalogue_produits",
    "fields": [
      {"accessor": "sku", "title": "Référence"},
      {"accessor": "name", "title": "Désignation"},
      {"accessor": "category.name", "title": "Catégorie"},
      {"accessor": "price", "title": "Prix HT"}
    ],
    "variables": {
      "is_active__exact": true
    },
    "ordering": ["category__name", "name"]
  }' \
  --output catalogue_produits.xlsx
```

### Export JavaScript (Fetch)

```javascript
async function exportProducts(filters) {
  const response = await fetch("/api/v1/export/", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${getAccessToken()}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      app_name: "store",
      model_name: "Product",
      file_extension: "xlsx",
      variables: filters,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message);
  }

  // Télécharger le fichier
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "export.xlsx";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
```

### Export Asynchrone avec Polling

```javascript
async function exportLargeDataset(options) {
  // Lancer l'export async
  const response = await fetch("/api/v1/export/", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${getAccessToken()}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ...options,
      async: true,
    }),
  });

  const job = await response.json();

  // Polling du statut
  while (true) {
    await new Promise((r) => setTimeout(r, 2000)); // 2s

    const statusRes = await fetch(job.status_url, {
      headers: { Authorization: `Bearer ${getAccessToken()}` },
    });
    const status = await statusRes.json();

    updateProgress(status.progress);

    if (status.status === "completed") {
      // Télécharger
      window.location.href = job.download_url;
      break;
    }

    if (status.status === "failed") {
      throw new Error(status.error);
    }
  }
}
```

---

## Bonnes Pratiques

### 1. Limitez les Champs Exposés

```python
# ✅ Allowlist explicite
"allowed_fields": {
    "store.Product": ["id", "name", "price"],
}

# ❌ Ne pas autoriser tous les champs par défaut
```

### 2. Utilisez des Templates

```python
# ✅ Templates pour les exports récurrents
EXPORT_TEMPLATES = {
    "monthly_sales": {...},
    "inventory_report": {...},
}
```

### 3. Configurez les Limites

```python
# ✅ Limites différenciées par format
"max_rows_csv": 100000,  # CSV peut gérer plus
"max_rows_xlsx": 10000,  # Excel limité

# ✅ Utilisez async pour les gros volumes
"async_threshold": 5000,
```

### 4. Auditez les Exports

```python
# Les exports sont automatiquement loggés
# event_type: "export_requested"
# metadata: { model, row_count, user, etc. }
```

📖 Voir [Audit & Logging](./audit.md).

---

## Voir Aussi

- [Reporting & BI](./reporting.md) - Agrégations et datasets
- [Génération PDF](./templating.md) - Exports PDF personnalisés
- [Permissions](../security/permissions.md) - Contrôle d'accès aux exports
