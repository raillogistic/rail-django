# Optimisation des Requêtes

## Vue d'Ensemble

Rail Django inclut des optimisations automatiques pour éviter le problème N+1 et améliorer les performances des requêtes GraphQL. Ce guide couvre les mécanismes intégrés et les configurations avancées.

---

## Table des Matières

1. [Optimisation Automatique](#optimisation-automatique)
2. [Configuration](#configuration)
3. [DataLoader](#dataloader)
4. [Limites de Complexité](#limites-de-complexité)
5. [Profiling et Debugging](#profiling-et-debugging)
6. [Bonnes Pratiques](#bonnes-pratiques)

---

## Optimisation Automatique

### Le Problème N+1

Sans optimisation, une requête GraphQL peut générer des centaines de requêtes SQL :

```graphql
# Cette requête naïve génèrerait 1 + N requêtes
query {
  products(limit: 100) {
    name
    category {
      name
    } # 100 requêtes supplémentaires !
  }
}
```

### Solution Rail Django

Le framework analyse les champs demandés et injecte automatiquement les optimisations :

```python
# Rail Django génère automatiquement :
Product.objects.select_related("category").only("id", "name", "category__name")
```

### Mécanismes d'Optimisation

| Mécanisme          | Cas d'Usage            | Résultat              |
| ------------------ | ---------------------- | --------------------- |
| `select_related`   | ForeignKey, OneToOne   | JOIN SQL              |
| `prefetch_related` | ManyToMany, reverse FK | Requête batch         |
| `only()`           | Tous les champs        | Sélection de colonnes |
| `defer()`          | Champs volumineux      | Exclusion de colonnes |

---

## Configuration

### Paramètres de Performance

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL = {
    "performance_settings": {
        # ─── Optimisation des QuerySets ───
        "enable_query_optimization": True,
        "enable_select_related": True,
        "enable_prefetch_related": True,
        "enable_only_fields": True,
        "enable_defer_fields": False,  # Désactivé par défaut

        # ─── DataLoader ───
        "enable_dataloader": True,
        "dataloader_batch_size": 100,

        # ─── Limites ───
        "max_query_depth": 10,
        "max_query_complexity": 1000,

        # ─── Analyse de Coût ───
        "enable_query_cost_analysis": False,

        # ─── Timeout ───
        "query_timeout": 30,
    },
}
```

### Désactivation par Modèle

```python
class LargeReport(models.Model):
    class GraphQLMeta:
        # Désactiver l'optimisation auto pour ce modèle
        enable_optimization = False

        # Ou personnaliser
        select_related = ["user"]
        prefetch_related = ["items"]
        only_fields = ["id", "title", "status"]
```

---

## DataLoader

### Fonctionnement

DataLoader résout le problème N+1 pour les cas où `select_related` ne suffit pas :

```python
# Sans DataLoader : N requêtes pour N objets
for order in orders:
    customer = order.customer  # Requête par order

# Avec DataLoader : 1 requête batch
customers = Customer.objects.filter(id__in=[o.customer_id for o in orders])
```

### Activation

```python
RAIL_DJANGO_GRAPHQL = {
    "performance_settings": {
        "enable_dataloader": True,
        "dataloader_batch_size": 100,
    },
}
```

### Cas d'Usage

DataLoader est particulièrement utile pour :

- Relations avec conditions complexes
- Propriétés calculées accédant à la DB
- Relations polymorphiques
- Appels à des services externes

### Custom DataLoader

```python
from graphene import ObjectType, Field
from promise import Promise
from promise.dataloader import DataLoader

class CustomerLoader(DataLoader):
    """
    DataLoader personnalisé pour les clients.
    """
    def batch_load_fn(self, customer_ids):
        customers = Customer.objects.filter(id__in=customer_ids)
        customer_map = {c.id: c for c in customers}
        return Promise.resolve([
            customer_map.get(cid) for cid in customer_ids
        ])

class OrderType(ObjectType):
    customer = Field(CustomerType)

    def resolve_customer(self, info):
        # Utiliser le loader depuis le contexte
        return info.context.loaders.customer.load(self.customer_id)
```

---

## Limites de Complexité

### Profondeur de Requête

Limite l'imbrication des relations :

```python
"max_query_depth": 10
```

```graphql
# Profondeur 4 - OK
query {
  orders {
    customer {
      company {
        address { city }
      }
    }
  }
}

# Profondeur > 10 - Rejeté
query {
  orders {
    customer {
      orders {
        customer {
          # ... trop profond
        }
      }
    }
  }
}
```

### Complexité de Requête

Chaque champ a un coût calculé :

```python
"max_query_complexity": 1000
```

| Type de Champ | Coût par Défaut |
| ------------- | --------------- |
| Scalaire      | 1               |
| Relation (FK) | 5               |
| Liste         | 10 × limit      |
| Liste paginée | 10 × page_size  |

### Configuration des Coûts

```python
class Order(models.Model):
    class GraphQLMeta:
        field_costs = {
            "items": 5,           # Relation coûte 5
            "total_calculated": 2, # Propriété calculée coûte 2
        }
        max_complexity = 500      # Limite spécifique au modèle
```

### Réponse avec Complexité

```json
{
  "data": { ... },
  "extensions": {
    "complexity": {
      "cost": 142,
      "limit": 1000,
      "depth": 4,
      "max_depth": 10
    }
  }
}
```

---

## Profiling et Debugging

### Middleware de Performance

```python
RAIL_DJANGO_GRAPHQL = {
    "middleware_settings": {
        "enable_performance_middleware": True,
        "log_performance": True,
        "performance_threshold_ms": 1000,  # Alerte si > 1s
    },
}
```

### Headers de Performance

Activez les headers pour le debugging :

```python
# Environnement
GRAPHQL_PERFORMANCE_HEADERS = True
```

```http
X-GraphQL-Duration: 45ms
X-GraphQL-SQL-Queries: 3
X-GraphQL-Complexity: 142
```

### Django Debug Toolbar

En développement, utilisez le toolbar pour analyser les requêtes :

```python
# settings/dev.py
INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
```

### Logging SQL

```python
# settings/dev.py
LOGGING = {
    "version": 1,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "loggers": {
        "django.db.backends": {
            "level": "DEBUG",
            "handlers": ["console"],
        },
    },
}
```

### Query Explain

Analysez les plans d'exécution SQL :

```python
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("EXPLAIN ANALYZE SELECT ...")
    print(cursor.fetchall())
```

---

## Bonnes Pratiques

### 1. Indexation

```python
class Order(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, db_index=True)
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["status", "-created_at"]),
        ]
```

### 2. Évitez les Propriétés N+1

```python
# ❌ Mauvais : N+1 dans une propriété
@property
def order_count(self):
    return self.orders.count()  # Requête à chaque accès !

# ✅ Bon : Annotation dans la query
queryset = Customer.objects.annotate(
    order_count=Count("orders")
)
```

### 3. Limitez les Listes

```python
RAIL_DJANGO_GRAPHQL = {
    "query_settings": {
        "default_page_size": 20,
        "max_page_size": 100,  # Pas plus de 100 items
    },
}
```

### 4. Utilisez only() pour les Gros Champs

```python
class Document(models.Model):
    content = models.TextField()  # Potentiellement gros

    class GraphQLMeta:
        defer_fields = ["content"]  # Différer le chargement
```

### 5. Cachez les Calculs Coûteux

```python
from django.core.cache import cache

class Dashboard:
    @property
    def expensive_stats(self):
        cache_key = f"dashboard_stats_{self.id}"
        stats = cache.get(cache_key)

        if stats is None:
            stats = self._calculate_stats()
            cache.set(cache_key, stats, timeout=300)

        return stats
```

### 6. Monitoring Continu

```python
# Alertez sur les requêtes lentes
RAIL_DJANGO_GRAPHQL = {
    "middleware_settings": {
        "performance_threshold_ms": 500,
    },
    "monitoring_settings": {
        "enable_metrics": True,
        "metrics_backend": "prometheus",
    },
}
```

---

## Voir Aussi

- [Rate Limiting](./rate-limiting.md) - Limitation de débit
- [Configuration](../graphql/configuration.md) - Tous les paramètres
- [Déploiement Production](../deployment/production.md) - Optimisations serveur
