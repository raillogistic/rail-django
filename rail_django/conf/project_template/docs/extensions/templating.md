# Génération PDF (Templating)

## Vue d'Ensemble

Rail Django inclut un moteur de templates PDF qui convertit des templates HTML/CSS en documents PDF. Il supporte les templates de modèles, les templates de fonctions, le rendu asynchrone et le post-processing (watermarks, signatures).

---

## Table des Matières

1. [Configuration](#configuration)
2. [Templates de Modèles](#templates-de-modèles)
3. [Templates de Fonctions](#templates-de-fonctions)
4. [Endpoints REST](#endpoints-rest)
5. [Rendu Asynchrone](#rendu-asynchrone)
6. [Post-Processing](#post-processing)
7. [API Programmatique](#api-programmatique)
8. [Bonnes Pratiques](#bonnes-pratiques)

---

## Configuration

### Paramètres de Templating

```python
# root/settings/base.py
RAIL_DJANGO_GRAPHQL_TEMPLATING = {
    # ─── Rendu ───
    "renderer": "weasyprint",  # "weasyprint" ou "wkhtmltopdf"
    "default_template_config": {
        "page_size": "A4",
        "margin": "2cm",
        "font_family": "Helvetica",
    },

    # ─── Sécurité ───
    "url_fetcher_allowlist": [
        "https://cdn.example.com/",
        "file:///static/",
    ],
    "max_render_time_seconds": 60,

    # ─── Endpoints ───
    "enable_catalog": True,      # GET /api/templates/catalog/
    "enable_preview": True,      # GET /api/templates/preview/.../

    # ─── Rate Limiting ───
    "rate_limit_per_minute": 30,

    # ─── Async ───
    "async_jobs": {
        "enable": False,
        "storage": "default",  # Ou "s3"
        "expiry_hours": 24,
    },

    # ─── Post-Processing ───
    "post_processing": {
        "watermark": {
            "enable": False,
            "text": "CONFIDENTIEL",
            "opacity": 0.3,
        },
        "encryption": {
            "enable": False,
            "user_password": None,
            "owner_password": None,
        },
    },
}
```

### Dépendances Optionnelles

```txt
# requirements/base.txt
weasyprint>=60.0           # Moteur de rendu principal
pypdf>=4.0.0               # Post-processing (watermarks, encryption)
pyhanko>=0.21.0            # Signatures numériques
```

---

## Templates de Modèles

### Décorateur @model_pdf_template

Associez un template PDF à un modèle Django :

```python
# apps/store/models.py
from django.db import models
from rail_django.extensions.templating import model_pdf_template

class Order(models.Model):
    """
    Modèle Commande avec templates PDF.
    """
    reference = models.CharField("Référence", max_length=50)
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE)
    total = models.DecimalField("Total", max_digits=10, decimal_places=2)

    @model_pdf_template(content="pdf/invoice.html")
    def download_invoice(self):
        """
        Génère une facture PDF pour cette commande.

        Returns:
            Contexte de template pour le rendu.
        """
        return {
            "order": self,
            "items": self.items.select_related("product"),
            "company": get_company_info(),
        }

    @model_pdf_template(
        content="pdf/packing_slip.html",
        filename="bon_livraison_{reference}.pdf",
        config={
            "page_size": "A4",
            "margin": "1.5cm",
        },
    )
    def download_packing_slip(self):
        """
        Génère un bon de livraison.
        """
        return {
            "order": self,
            "items": self.items.all(),
        }
```

### Options du Décorateur

| Option     | Type | Description                                      |
| ---------- | ---- | ------------------------------------------------ |
| `content`  | str  | Chemin du template HTML (dans `templates/`)      |
| `filename` | str  | Nom du fichier généré (supporte les variables)   |
| `config`   | dict | Configuration de rendu (page_size, margin, etc.) |

### URL Générée

```
GET /api/templates/store/order/download_invoice/<pk>/
GET /api/templates/store/order/download_packing_slip/<pk>/
```

---

## Templates de Fonctions

### Décorateur @pdf_template

Pour les PDFs non liés à un modèle spécifique :

```python
# apps/reports/views.py
from rail_django.extensions.templating import pdf_template

@pdf_template(
    content="pdf/monthly_report.html",
    url="reports/monthly",  # URL personnalisée
    filename="rapport_mensuel_{year}_{month}.pdf",
)
def monthly_report(request, year, month):
    """
    Génère un rapport mensuel.

    Args:
        year: Année du rapport.
        month: Mois du rapport.

    Returns:
        Contexte de template.
    """
    orders = Order.objects.filter(
        created_at__year=year,
        created_at__month=month,
    )

    return {
        "year": year,
        "month": month,
        "orders": orders,
        "total_revenue": orders.aggregate(Sum("total"))["total__sum"],
    }
```

### Chargement au Démarrage

Assurez-vous que le module est importé au démarrage :

```python
# apps/reports/apps.py
from django.apps import AppConfig

class ReportsConfig(AppConfig):
    name = "apps.reports"

    def ready(self):
        # Importe les templates PDF
        from . import views  # noqa
```

### URL Générée

```
GET /api/templates/reports/monthly/<year>/<month>/
```

---

## Endpoints REST

### Catalogue des Templates

```http
GET /api/templates/catalog/
Authorization: Bearer <jwt>
```

**Réponse :**

```json
{
  "templates": [
    {
      "key": "store.order.download_invoice",
      "title": "Facture",
      "model": "store.Order",
      "endpoint": "/api/templates/store/order/download_invoice/{pk}/"
    },
    {
      "key": "reports.monthly_report",
      "title": "Rapport Mensuel",
      "model": null,
      "endpoint": "/api/templates/reports/monthly/{year}/{month}/"
    }
  ]
}
```

### Rendu PDF

```http
GET /api/templates/store/order/download_invoice/42/
Authorization: Bearer <jwt>
```

**Réponse :**

```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice_42.pdf"

%PDF-1.4
[binary data]
```

### Preview HTML (Dev)

```http
GET /api/templates/preview/store/order/download_invoice/42/
Authorization: Bearer <jwt>
```

Retourne le HTML rendu (sans conversion PDF).

---

## Rendu Asynchrone

Pour les PDFs lourds ou les gros volumes.

### Activation

```python
RAIL_DJANGO_GRAPHQL_TEMPLATING = {
    "async_jobs": {
        "enable": True,
        "storage": "s3",  # Ou "default" (système de fichiers)
        "expiry_hours": 24,
    },
}
```

### Requête Async

```http
GET /api/templates/store/order/download_invoice/42/?async=true
Authorization: Bearer <jwt>
```

**Réponse :**

```json
{
  "job_id": "tpl_a1b2c3d4",
  "status": "pending",
  "status_url": "/api/templates/jobs/tpl_a1b2c3d4/",
  "download_url": "/api/templates/jobs/tpl_a1b2c3d4/download/"
}
```

### Vérification du Statut

```http
GET /api/templates/jobs/tpl_a1b2c3d4/
Authorization: Bearer <jwt>
```

```json
{
  "job_id": "tpl_a1b2c3d4",
  "status": "completed",
  "created_at": "2026-01-16T10:30:00Z",
  "completed_at": "2026-01-16T10:30:15Z"
}
```

### Téléchargement

```http
GET /api/templates/jobs/tpl_a1b2c3d4/download/
```

---

## Post-Processing

### Watermarks

```python
RAIL_DJANGO_GRAPHQL_TEMPLATING = {
    "post_processing": {
        "watermark": {
            "enable": True,
            "text": "CONFIDENTIEL",
            "opacity": 0.3,
            "angle": 45,
            "font_size": 60,
            "color": "#CCCCCC",
        },
    },
}
```

### Watermark Image

```python
"watermark": {
    "enable": True,
    "image": "/static/images/watermark.png",
    "opacity": 0.2,
    "position": "center",  # "center", "top", "bottom"
}
```

### Encryption (Mot de Passe)

```python
"encryption": {
    "enable": True,
    "user_password": "lecture_seule",  # Pour ouvrir le PDF
    "owner_password": "admin_password", # Pour modifier
    "permissions": ["print", "copy"],   # Permissions accordées
}
```

### Signature Numérique

Nécessite `pyhanko` et un certificat :

```python
"signature": {
    "enable": True,
    "certificate_path": "/path/to/certificate.p12",
    "certificate_password": os.environ.get("CERT_PASSWORD"),
    "reason": "Document généré automatiquement",
    "location": "Paris, France",
}
```

### Page Stamps

Ajoutez des numéros de page ou autres informations :

```python
"page_stamp": {
    "enable": True,
    "template": "Page {page} sur {total}",
    "position": "bottom-center",  # Position sur la page
    "font_size": 10,
}
```

---

## API Programmatique

### render_pdf Helper

```python
from rail_django.extensions.templating import render_pdf

# Rendu simple
pdf_bytes = render_pdf(
    template="pdf/invoice.html",
    context={"order": order, "items": items},
)

# Avec options
pdf_bytes = render_pdf(
    template="pdf/report.html",
    context={"data": report_data},
    filename="report.pdf",
    config={
        "page_size": "A3",
        "orientation": "landscape",
        "margin": "1cm",
    },
)

# Sauvegarder
with open("output.pdf", "wb") as f:
    f.write(pdf_bytes)
```

### PdfBuilder Class

Pour plus de contrôle :

```python
from rail_django.extensions.templating import PdfBuilder

builder = PdfBuilder(
    template="pdf/invoice.html",
    context={"order": order},
)

# Configurer
builder.set_page_size("A4")
builder.set_margins(top="2cm", bottom="2cm", left="1.5cm", right="1.5cm")

# Post-processing
builder.add_watermark("BROUILLON", opacity=0.2)
builder.add_page_numbers(format="Page {page}/{total}")

# Générer
pdf_bytes = builder.render()
```

### Commande Management

```bash
# Générer un PDF depuis la ligne de commande
python manage.py render_pdf pdf/invoice.html --pk 42 --output facture_42.pdf

# Avec contexte personnalisé
python manage.py render_pdf pdf/report.html \
    --context '{"title": "Rapport Q1"}' \
    --output rapport.pdf
```

---

## Structure des Templates

### Template HTML Basique

```html
<!-- templates/pdf/invoice.html -->
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Facture {{ order.reference }}</title>
    <style>
      @page {
        size: A4;
        margin: 2cm;
      }

      body {
        font-family: Helvetica, Arial, sans-serif;
        font-size: 12pt;
        line-height: 1.4;
      }

      .header {
        display: flex;
        justify-content: space-between;
        margin-bottom: 2cm;
      }

      .logo {
        max-width: 150px;
      }

      table {
        width: 100%;
        border-collapse: collapse;
      }

      th,
      td {
        padding: 8px;
        border-bottom: 1px solid #ddd;
        text-align: left;
      }

      .total-row {
        font-weight: bold;
        font-size: 14pt;
      }

      /* Saut de page */
      .page-break {
        page-break-after: always;
      }
    </style>
  </head>
  <body>
    <div class="header">
      <img src="{{ company.logo_url }}" class="logo" alt="Logo" />
      <div class="invoice-info">
        <h1>Facture {{ order.reference }}</h1>
        <p>Date: {{ order.created_at|date:"d/m/Y" }}</p>
      </div>
    </div>

    <div class="customer">
      <h3>Client</h3>
      <p>
        {{ order.customer.name }}<br />
        {{ order.customer.address }}
      </p>
    </div>

    <table>
      <thead>
        <tr>
          <th>Article</th>
          <th>Qté</th>
          <th>Prix unitaire</th>
          <th>Total</th>
        </tr>
      </thead>
      <tbody>
        {% for item in items %}
        <tr>
          <td>{{ item.product.name }}</td>
          <td>{{ item.quantity }}</td>
          <td>{{ item.unit_price|floatformat:2 }} €</td>
          <td>{{ item.total|floatformat:2 }} €</td>
        </tr>
        {% endfor %}
      </tbody>
      <tfoot>
        <tr class="total-row">
          <td colspan="3">Total TTC</td>
          <td>{{ order.total|floatformat:2 }} €</td>
        </tr>
      </tfoot>
    </table>
  </body>
</html>
```

---

## Bonnes Pratiques

### 1. Optimisez les Templates

```html
<!-- ✅ Embedez les images en base64 pour éviter les requêtes -->
<img src="data:image/png;base64,{{ logo_base64 }}" />

<!-- ✅ CSS inline pour performance -->
<style>
  /* styles ici */
</style>

<!-- ❌ Évitez les ressources externes -->
<link href="https://fonts.googleapis.com/..." />
```

### 2. Sécurisez les URLs

```python
# ✅ Allowlist des URL fetchables
"url_fetcher_allowlist": [
    "https://cdn.internal.corp/",
    "file:///app/static/",
],
```

### 3. Gérez les Gros PDFs

```python
# ✅ Utilisez le mode async pour les gros documents
"async_jobs": {
    "enable": True,
    "threshold_pages": 50,  # Auto-async si > 50 pages
}
```

### 4. Tests

```python
from django.test import TestCase
from rail_django.extensions.templating import render_pdf

class PdfTests(TestCase):
    def test_invoice_renders(self):
        order = Order.objects.create(...)
        pdf = render_pdf("pdf/invoice.html", {"order": order})

        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 1000)
```

---

## Voir Aussi

- [Export de Données](./exporting.md) - Export CSV/Excel
- [Reporting](./reporting.md) - Génération de rapports
- [Configuration](../graphql/configuration.md) - Paramètres complets
