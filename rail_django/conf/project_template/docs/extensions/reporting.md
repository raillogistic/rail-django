# Reporting & BI

## Vue d'Ensemble

Le module Reporting de Rail Django permet de définir des datasets analytiques, des visualisations et des rapports complets, le tout exposé via GraphQL. Il supporte les agrégations, les transformations de colonnes et les fonctionnalités PostgreSQL avancées.

---

## Table des Matières

1. [Concepts](#concepts)
2. [Définition d'un Dataset](#définition-dun-dataset)
3. [Dimensions et Transformations](#dimensions-et-transformations)
4. [Métriques et Agrégations](#métriques-et-agrégations)
5. [Exécution des Requêtes](#exécution-des-requêtes)
6. [Visualisations](#visualisations)
7. [Rapports](#rapports)
8. [API GraphQL](#api-graphql)
9. [Bonnes Pratiques](#bonnes-pratiques)

---

## Concepts

### Architecture

```
ReportingDataset       → Définition sémantique sur un modèle Django
    └── dimensions[]   → Colonnes de groupement
    └── metrics[]      → Agrégations calculées
    └── computed_fields[] → Champs calculés post-agrégation

ReportingVisualization → Configuration de graphique/tableau
    └── dataset        → Référence au dataset
    └── config         → Paramètres de visualisation

ReportingReport        → Dashboard composé de visualisations
    └── visualizations[] → Liste ordonnée de visualisations
```

### Modèles Django

- `ReportingDataset` : Définit une couche sémantique sur un modèle.
- `ReportingVisualization` : Sauvegarde des configurations de graphiques.
- `ReportingReport` : Agrège plusieurs visualisations.
- `ReportingExportJob` : Captures de snapshots pour export.

---

## Définition d'un Dataset

### Création Basique

```python
from rail_django.extensions.reporting import ReportingDataset

dataset = ReportingDataset.objects.create(
    code="monthly_sales",
    title="Ventes Mensuelles",
    description="Analyse des ventes par mois et région",
    source_app_label="store",
    source_model="Order",

    # Dimensions : colonnes de regroupement
    dimensions=[
        {"name": "month", "field": "created_at", "transform": "trunc:month"},
        {"name": "region", "field": "customer__region"},
    ],

    # Métriques : agrégations
    metrics=[
        {"name": "total_revenue", "field": "total", "aggregation": "sum"},
        {"name": "order_count", "field": "id", "aggregation": "count"},
        {"name": "avg_order_value", "field": "total", "aggregation": "avg"},
    ],
)
```

### Configuration Avancée

```python
dataset = ReportingDataset.objects.create(
    code="customer_analytics",
    title="Analyse Clients",
    source_app_label="crm",
    source_model="Customer",

    dimensions=[
        {"name": "city", "field": "city"},
        {"name": "signup_month", "field": "created_at", "transform": "trunc:month"},
    ],

    metrics=[
        {"name": "customer_count", "field": "pk", "aggregation": "count"},
        {"name": "avg_balance", "field": "account_balance", "aggregation": "avg"},
    ],

    # Champs calculés post-agrégation
    computed_fields=[
        {
            "name": "balance_per_customer",
            "formula": "avg_balance / customer_count",
        },
    ],

    # Filtres par défaut (toujours appliqués)
    default_filters=[
        {"field": "is_active", "lookup": "exact", "value": True},
    ],

    # Métadonnées de sécurité et configuration
    metadata={
        "allow_ad_hoc": False,  # Pas de requêtes libres
        "allowed_fields": ["is_active", "city"],  # Filtres autorisés
        "record_fields": ["name", "email", "city"],  # Mode records
        "quick_fields": ["name", "email"],  # Recherche rapide
        "max_limit": 2000,
        "cache_ttl_seconds": 60,
    },
)
```

---

## Dimensions et Transformations

### Définition d'une Dimension

```python
{
    "name": "alias_dimension",  # Nom dans le résultat
    "field": "model_field",     # Champ Django
    "transform": "...",         # Transformation optionnelle
}
```

### Transformations Disponibles

| Transform       | Description          | Exemple              |
| --------------- | -------------------- | -------------------- |
| `lower`         | Minuscules           | `"paris"`            |
| `upper`         | Majuscules           | `"PARIS"`            |
| `date`          | Date seule           | `2026-01-16`         |
| `trunc:hour`    | Arrondi à l'heure    | `2026-01-16 10:00`   |
| `trunc:day`     | Arrondi au jour      | `2026-01-16`         |
| `trunc:week`    | Arrondi à la semaine | `2026-01-13` (lundi) |
| `trunc:month`   | Arrondi au mois      | `2026-01-01`         |
| `trunc:quarter` | Arrondi au trimestre | `2026-01-01`         |
| `trunc:year`    | Arrondi à l'année    | `2026-01-01`         |
| `year`          | Extraction année     | `2026`               |
| `quarter`       | Extraction trimestre | `1`                  |
| `month`         | Extraction mois      | `1`                  |
| `week`          | Extraction semaine   | `3`                  |
| `weekday`       | Jour de la semaine   | `4` (jeudi)          |
| `day`           | Extraction jour      | `16`                 |

### Exemple Multi-Dimensions

```python
dimensions=[
    {"name": "year", "field": "created_at", "transform": "year"},
    {"name": "month", "field": "created_at", "transform": "month"},
    {"name": "category", "field": "product__category__name"},
    {"name": "region", "field": "customer__address__region", "transform": "upper"},
]
```

---

## Métriques et Agrégations

### Définition d'une Métrique

```python
{
    "name": "metric_alias",     # Nom dans le résultat
    "field": "model_field",     # Champ à agréger
    "aggregation": "sum",       # Type d'agrégation
    "options": {},              # Options spécifiques
}
```

### Agrégations Standards

| Agrégation       | Description       | SQL                     |
| ---------------- | ----------------- | ----------------------- |
| `count`          | Nombre d'éléments | `COUNT(*)`              |
| `distinct_count` | Nombre distinct   | `COUNT(DISTINCT field)` |
| `sum`            | Somme             | `SUM(field)`            |
| `avg`            | Moyenne           | `AVG(field)`            |
| `min`            | Minimum           | `MIN(field)`            |
| `max`            | Maximum           | `MAX(field)`            |

### Agrégations PostgreSQL

Disponibles uniquement avec PostgreSQL :

| Agrégation   | Description      | Options                 |
| ------------ | ---------------- | ----------------------- |
| `array_agg`  | Liste de valeurs | `distinct`, `ordering`  |
| `string_agg` | Concaténation    | `delimiter`, `distinct` |
| `jsonb_agg`  | Agrégation JSONB |                         |
| `bool_and`   | AND logique      |                         |
| `bool_or`    | OR logique       |                         |
| `bit_and`    | AND bit à bit    |                         |
| `bit_or`     | OR bit à bit     |                         |
| `bit_xor`    | XOR bit à bit    |                         |

### Exemple avec Options

```python
metrics=[
    # Liste d'emails distincts, triés
    {
        "name": "customer_emails",
        "field": "customer__email",
        "aggregation": "string_agg",
        "options": {
            "delimiter": "; ",
            "distinct": True,
            "ordering": ["customer__email"],
        },
    },
    # Liste de produits
    {
        "name": "products",
        "field": "product__name",
        "aggregation": "array_agg",
        "options": {
            "distinct": True,
        },
    },
]
```

---

## Exécution des Requêtes

### Méthode Preview

Exécute une requête rapide avec les dimensions/métriques par défaut :

```python
# Requête simple
result = dataset.preview()

# Avec filtres et options
result = dataset.preview(
    quick="recherche",          # Recherche rapide
    limit=50,
    ordering="-total_revenue",
    filters=[
        {"field": "region", "lookup": "exact", "value": "IDF"},
    ],
)
```

### Méthode run_query

Pour des requêtes dynamiques avec override des dimensions/métriques :

```python
# Mode agrégation (défaut)
spec = {
    "dimensions": ["month", "category"],
    "metrics": ["total_revenue", "order_count"],
    "filters": [
        {"field": "is_active", "lookup": "exact", "value": True},
    ],
    "having": [
        {"field": "order_count", "lookup": "gte", "value": 5},
    ],
    "ordering": ["-total_revenue"],
    "limit": 100,
    "offset": 0,
}
result = dataset.run_query(spec)
```

### Mode Records

Pour obtenir des lignes individuelles au lieu d'agrégations :

```python
spec = {
    "mode": "records",
    "fields": ["name", "email", "city", "created_at"],
    "filters": [
        {"field": "is_active", "lookup": "exact", "value": True},
    ],
    "ordering": ["-created_at"],
    "limit": 100,
}
result = dataset.run_query(spec)
```

### Syntaxe des Filtres Avancée

#### Liste Simple

```python
filters=[
    {"field": "status", "lookup": "exact", "value": "active"},
    {"field": "created_at", "lookup": "gte", "value": "2026-01-01"},
]
```

#### Arbre de Conditions

```python
filters={
    "op": "and",
    "items": [
        {"field": "is_active", "lookup": "exact", "value": True},
        {
            "op": "or",
            "items": [
                {"field": "city", "lookup": "icontains", "value": "paris"},
                {"field": "city", "lookup": "icontains", "value": "lyon"},
            ],
        },
    ],
}
```

---

## Visualisations

### Création d'une Visualisation

```python
from rail_django.extensions.reporting import ReportingVisualization

viz = ReportingVisualization.objects.create(
    dataset=dataset,
    code="sales_by_region",
    title="Ventes par Région",
    kind="bar",  # bar, line, pie, table, area, scatter

    config={
        # Requête embarquée
        "query": {
            "dimensions": ["region"],
            "metrics": ["total_revenue", "order_count"],
            "ordering": ["-total_revenue"],
            "limit": 10,
        },

        # Configuration du graphique
        "x_axis": "region",
        "y_axis": "total_revenue",
        "series": "order_count",

        # Options visuelles
        "colors": ["#4A90D9", "#E94E77"],
        "show_legend": True,
        "show_values": True,
    },
)
```

### Rendu

```python
# Rendu avec les paramètres par défaut
payload = viz.render()

# Rendu avec filtres runtime
payload = viz.render(
    quick="",
    limit=20,
    filters=[{"field": "year", "lookup": "exact", "value": 2026}],
)
```

### Types de Visualisations

| Kind      | Description         |
| --------- | ------------------- |
| `bar`     | Graphique en barres |
| `line`    | Graphique linéaire  |
| `area`    | Graphique en aires  |
| `pie`     | Camembert           |
| `donut`   | Anneau              |
| `scatter` | Nuage de points     |
| `table`   | Tableau de données  |
| `metric`  | Valeur unique (KPI) |

---

## Rapports

### Création d'un Rapport

```python
from rail_django.extensions.reporting import ReportingReport

report = ReportingReport.objects.create(
    code="monthly_overview",
    title="Vue d'Ensemble Mensuelle",
    description="Dashboard des ventes et clients",
)

# Associer des visualisations
report.visualizations.add(viz_sales, viz_customers, viz_products)
```

### Construction du Payload

```python
payload = report.build_payload(
    quick="",
    limit=100,
    filters=[{"field": "month", "lookup": "exact", "value": "2026-01"}],
)
```

**Structure du Payload :**

```python
{
    "report": {
        "code": "monthly_overview",
        "title": "Vue d'Ensemble Mensuelle",
    },
    "generated_at": "2026-01-16T10:30:00Z",
    "visualizations": [
        {
            "code": "sales_by_region",
            "title": "Ventes par Région",
            "kind": "bar",
            "data": [
                {"region": "IDF", "total_revenue": 150000, "order_count": 450},
                {"region": "PACA", "total_revenue": 85000, "order_count": 280},
            ],
        },
        # ... autres visualisations
    ],
}
```

---

## API GraphQL

### Query Dataset

```graphql
query SalesData($code: String!, $spec: QuerySpec) {
  reporting_dataset(code: $code) {
    code
    title

    # Exécuter une requête
    run_query(spec: $spec) {
      data
      total_count
      execution_time_ms
    }

    # Preview rapide
    preview(limit: 100) {
      data
    }
  }
}
```

### Query Visualisation

```graphql
query ChartData($code: String!) {
  reporting_visualization(code: $code) {
    code
    title
    kind

    render {
      data
      config
    }
  }
}
```

### Query Rapport Complet

```graphql
query DashboardData($code: String!, $filters: [FilterInput]) {
  reporting_report(code: $code) {
    build_payload(filters: $filters) {
      generated_at
      visualizations {
        code
        title
        kind
        data
      }
    }
  }
}
```

### Mutations d'Export

```graphql
mutation ExportDataset($code: String!, $format: String!) {
  export_dataset(code: $code, format: $format) {
    job_id
    status
    download_url
  }
}
```

---

## Bonnes Pratiques

### 1. Indexation

Indexez les colonnes utilisées dans les dimensions et filtres :

```python
class Order(models.Model):
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]
```

### 2. Caching

Configurez le cache pour les requêtes fréquentes :

```python
metadata={
    "cache_ttl_seconds": 300,  # 5 minutes
}
```

### 3. Limites

Protégez contre les requêtes coûteuses :

```python
metadata={
    "max_limit": 5000,
    "max_dimensions": 5,
}
```

### 4. Sécurité

Utilisez les allowlists pour contrôler l'accès :

```python
metadata={
    "allow_ad_hoc": False,  # Pas de requêtes libres
    "allowed_fields": ["status", "region"],  # Filtres autorisés
}
```

---

## Voir Aussi

- [Export de Données](./exporting.md) - Export CSV/Excel
- [Configuration](../graphql/configuration.md) - Paramètres reporting
- [Optimisation](../performance/optimization.md) - Performance des requêtes
