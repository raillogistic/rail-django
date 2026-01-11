# Rail Django: The Complete Guide

Welcome to the definitive documentation for **Rail Django**, the production-grade framework for building enterprise GraphQL APIs with Django.

This guide is designed to take you from a fresh installation to deploying a complex, secured, and high-performance API system.

---

## 📑 Table of Contents

1.  [Introduction & Philosophy](#1-introduction--philosophy)
2.  [Installation & Setup](#2-installation--setup)
    *   [Prerequisites](#prerequisites)
    *   [Quick Start](#quick-start)
    *   [Project Structure](#project-structure)
3.  [Core Architecture](#3-core-architecture)
    *   [Auto-Schema Generation](#auto-schema-generation)
    *   [The Registry System](#the-registry-system)
    *   [Resolvers & Mutations](#resolvers--mutations)
4.  [Configuration Guide](#4-configuration-guide)
    *   [Global Settings](#global-settings)
    *   [Multi-Schema Configuration](#multi-schema-configuration)
    *   [Environment Variables](#environment-variables)
5.  [Data Modeling & API Design](#5-data-modeling--api-design)
    *   [Defining Models](#defining-models)
    *   [Customizing GraphQL Types](#customizing-graphql-types)
    *   [The `graphql_meta` Class](#the-graphql_meta-class)
6.  [Querying & Filtering](#6-querying--filtering)
    *   [Advanced Filtering](#advanced-filtering)
    *   [Pagination Strategies](#pagination-strategies)
    *   [Ordering & Sorting](#ordering--sorting)
7.  [Mutations & Operations](#7-mutations--operations)
    *   [Auto-CRUD Mutations](#auto-crud-mutations)
    *   [Custom Mutations](#custom-mutations)
    *   [Bulk Operations](#bulk-operations)
8.  [Security & Permissions](#8-security--permissions)
    *   [Authentication Flow (JWT)](#authentication-flow-jwt)
    *   [Role-Based Access Control (RBAC)](#role-based-access-control-rbac)
    *   [Field-Level Security](#field-level-security)
    *   [Input Sanitization](#input-sanitization)
9.  [Extensions System](#9-extensions-system)
    *   [Audit Logging](#audit-logging)
    *   [Data Exporting (Excel/CSV)](#data-exporting-excelcsv)
    *   [Health Monitoring](#health-monitoring)
    *   [Multi-Factor Authentication (MFA)](#multi-factor-authentication-mfa)
    *   [PDF Templating Engine](#pdf-templating-engine)
10. [Performance Tuning](#10-performance-tuning)
    *   [Query Optimization](#query-optimization)
    *   [DataLoader & N+1 Problem](#dataloader--n1-problem)
    *   [Complexity Limiting](#complexity-limiting)
11. [Deployment & DevOps](#11-deployment--devops)
    *   [Docker Configuration](#docker-configuration)
    *   [Production Checklist](#production-checklist)
    *   [Troubleshooting](#troubleshooting)
12. [Manual Deployment Guide](#12-manual-deployment-guide)

---

## 1. Introduction & Philosophy

Rail Django exists to solve the "boilerplate fatigue" associated with Graphene-Django. While Graphene is powerful, building a standard CRUD API often requires writing hundreds of lines of repetitive `ObjectType`, `DjangoFilterConnectionField`, and `Mutation` classes.

**Our Philosophy:**
1.  **Convention over Configuration:** If you define a Django model, you should get a working API immediately.
2.  **Security by Design:** Permissions, depths limits, and input validation should be on by default.
3.  **Battery Included:** Audit logs, exports, and health checks are requirements, not "nice-to-haves".

---

## 2. Installation & Setup

### Prerequisites
*   Python 3.8 or higher
*   pip (Python Package Installer)
*   (Optional) Docker & Docker Compose for containerized development

### Quick Start

1.  **Install the library:**
    ```bash
    pip install rail-django
    # OR directly from source
    pip install git+https://github.com/raillogistic/rail-django.git
    ```

2.  **Bootstrap your project:**
    The `rail-admin` CLI tool sets up the perfect directory structure.
    ```bash
    rail-admin startproject my_platform
    cd my_platform
    ```

3.  **Initialize the Database:**
    ```bash
    python manage.py migrate
    ```

4.  **Create an Admin User:**
    ```bash
    python manage.py createsuperuser
    ```

5.  **Run the Server:**
    ```bash
    python manage.py runserver
    ```
    Access the GraphiQL playground at: `http://localhost:8000/graphql/graphiql/`

### Project Structure
Rail Django enforces a clean architecture to keep your codebase scalable.

```
my_platform/
├── manage.py           # Django entry point
├── root/               # Core configuration (formerly 'project_name')
│   ├── settings/       # Split settings (base, dev, prod)
│   ├── urls.py         # Global URL routing
│   └── wsgi.py         # WSGI entry point
├── apps/               # Directory for your Django apps
│   └── core/           # Example core app
├── requirements.txt    # Project dependencies
└── Dockerfile          # Production-ready Docker build
```

---

## 3. Core Architecture

### Auto-Schema Generation
At startup, Rail Django scans your `INSTALLED_APPS`. For every `models.Model` it finds, it:
1.  Creates a `DjangoObjectType`.
2.  Generates a `FilterSet` for advanced querying.
3.  Registers `list` and `retrieve` queries.
4.  Generates `create`, `update`, and `delete` mutations (if enabled).

### The Registry System
The `SchemaRegistry` is the brain of the framework. It holds references to all generated types and resolvers. You rarely interact with it directly, but it ensures that circular dependencies between models (e.g., User <-> Group) are resolved gracefully.

### Resolvers & Mutations
*   **Queries** use standard Django QuerySets. The framework automatically injects `select_related` and `prefetch_related` based on the requested fields to optimize performance.
*   **Mutations** wrap the Django Model `save()` method, ensuring signals (`pre_save`, `post_save`) are fired correctly. They also automatically handle input validation.

---

## 4. Configuration Guide

Your project is configured via `root/settings/base.py`. The primary configuration object is `RAIL_DJANGO_GRAPHQL`.

### Global Settings (`RAIL_DJANGO_GRAPHQL`)

```python
RAIL_DJANGO_GRAPHQL = {
    "schema_settings": {
        # Security: Disable introspection in production to hide schema details
        "enable_introspection": env.bool("DJANGO_DEBUG", default=False),
        
        # UI: Enable the GraphiQL playground only in dev
        "enable_graphiql": env.bool("DJANGO_DEBUG", default=False),
        
        # Access: Require JWT token for ALL queries by default
        "authentication_required": True,
        
        # Exclusions: Hide specific internal models
        "excluded_apps": ["admin", "contenttypes"],
    },
    "mutation_settings": {
        # CRUD: Globally enable/disable auto-generation
        "generate_create": True,
        "generate_update": True,
        "generate_delete": True,
        
        # Bulk: Enable bulk operations (e.g. delete 50 items)
        "enable_bulk_operations": False, 
    },
    "security_settings": {
        # Limits: Protect against DoS
        "max_query_depth": 10,
        "max_query_complexity": 2000,
        
        # Uploads: File limits
        "max_file_upload_size": 10 * 1024 * 1024, # 10MB
    }
}
```

### Schema Management API
The REST endpoints under `/api/v1/` require a JWT access token and admin
permissions.

```python
GRAPHQL_SCHEMA_API_REQUIRED_PERMISSIONS = ["rail_django.manage_schema"]
GRAPHQL_SCHEMA_API_RATE_LIMIT = {
    "enable": True,
    "window_seconds": 60,
    "max_requests": 60,
}
```

### Multi-Schema Configuration
For complex apps, you often need different APIs for different consumers (e.g., Public Auth, Mobile App, Admin Panel).

```python
# settings.py

RAIL_DJANGO_GRAPHQL_SCHEMAS = {
    "auth": {
        # Public endpoint for login/register
        "schema_settings": {
            "authentication_required": False,
            "enable_graphiql": False, 
        },
        # Disable unrelated mutations
        "mutation_settings": {
            "generate_create": False,
            "generate_update": False,
        }
    },
    "default": {
        # Main API for authenticated users
        "schema_settings": {
            "authentication_required": True,
        }
    },
    "admin": {
        # Internal tools API
        "schema_settings": {
            "authentication_required": True,
            "enable_graphiql": True, # Allow admins to explore
        },
        "mutation_settings": {
            "enable_bulk_operations": True,
        }
    }
}
```

This creates distinct endpoints (configured in `urls.py` automatically):
*   `/graphql/auth/`
*   `/graphql/gql/`
*   `/graphql/admin/`

#### How schemas are registered
Rail Django registers schemas from two sources, in this order:
1.  App discovery: each installed app is scanned for `schemas.py`,
    `graphql_schema.py`, `schema.py`, or `graphql/schema.py`. If a module exposes
    `register_schema(registry)`, it is called.
2.  Settings fallback: any entries in `RAIL_DJANGO_GRAPHQL_SCHEMAS` that are not
    already registered are added automatically.

By default, the starter template registers schemas only from
`RAIL_DJANGO_GRAPHQL_SCHEMAS`. The `schemas.py` and `graphql_schema.py` files
ship as no-op stubs unless you add `register_schema(...)` yourself. Schemas can
still appear even if `register_schema(...)` is empty, as long as they exist in
`RAIL_DJANGO_GRAPHQL_SCHEMAS`.

To disable a schema:
*   Remove the schema key from `RAIL_DJANGO_GRAPHQL_SCHEMAS`, or set
    `"enabled": False`.
*   If you also register it in `schemas.py`, remove it there too.

The registry is cached once per process. Restart the server (or call
`schema_registry.clear()` in a Django shell) to pick up changes.

---

## 5. Data Modeling & API Design

### Defining Models
Write standard Django models. Rail Django does the rest.

```python
# apps/store/models.py
from django.db import models

class Product(models.Model):
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=50, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name
```

### The `graphql_meta` Class
To customize how a specific model appears in the API, add a `graphql_meta` attribute. This is the **most powerful** feature for fine-grained control.

```python
from rail_django.core.meta import GraphQLMeta

class Product(models.Model):
    # ... fields ...
    
    graphql_meta = GraphQLMeta(
        # Exclude internal fields from the API
        exclude=["cost_price", "supplier_notes"],
        
        # Make specific fields read-only
        readonly_fields=["sku"],
        
        # Configure field-level permissions
        field_permissions={
            "profit_margin": {
                "roles": ["manager", "admin"],
                "level": "read"
            }
        },
        
        # Customize the lookup field (instead of ID)
        lookup_field="sku",
        
        # Add extra filter capabilities
        filter_fields={
            "price": ["gt", "lt", "range"],
            "name": ["icontains", "istartswith"]
        }
    )
```

---

## 6. Querying & Filtering

### Standard Queries
Rail Django generates plural (list) and singular (retrieve) fields.

**Request:**
```graphql
query {
  products(first: 10) {
    id
    name
    price
  }
  product(id: "123") {
    name
  }
}
```

### Advanced Filtering
The library includes a powerful filtering engine derived from `django-filter`.

**Exact Match:**
`products(is_active: true)`

**String Search (Case-Insensitive):**
`products(name_Icontains: "phone")`

**Range Filters:**
`products(price_Gt: 100, price_Lt: 500)`

**Related Fields:**
`products(category_Name_Icontains: "Electronics")`

### Pagination Strategies
By default, Rail Django uses Offset Pagination (limit/offset) which is simpler for most frontend frameworks.

**Request:**
```graphql
query {
  products(offset: 0, limit: 20) {
    id
    name
  }
}
```

*To enable Relay-style (Cursor) pagination, update `query_settings` in `settings.py`:*
```python
"query_settings": {
    "use_relay": True,
}
```

### Ordering
Sort results by any field.
`products(ordering: ["-price", "name"])` (High to low price, then A-Z)

---

## 7. Mutations & Operations

### Auto-CRUD Mutations
Enabled by default.

**Create:**
```graphql
mutation {
  createProduct(input: {name: "New Item", price: 99.99}) {
    ok
    product {
      id
      name
    }
    errors
  }
}
```

**Update:**
```graphql
mutation {
  updateProduct(id: "123", input: {price: 89.99}) {
    ok
    product { price }
  }
}
```

**Delete:**
```graphql
mutation {
  deleteProduct(id: "123") {
    ok
  }
}
```

### Custom Mutations
When you need logic beyond CRUD, define a method on your model and expose it.

**Model:**
```python
class Product(models.Model):
    # ...
    def apply_discount(self, percentage):
        self.price = self.price * (1 - percentage / 100)
        self.save()
        return self
```

**Settings/Meta:**
(Currently, custom mutation logic usually requires writing a manual Graphene mutation or using specific Rail Django decorators if available in your version. Check `rail_django.generators.mutations` for advanced method mapping).

### Bulk Operations
Enable `generate_bulk: True` in `mutation_settings`.

```graphql
mutation {
  bulkDeleteProduct(ids: ["1", "2", "3"]) {
    count
  }
}
```

---

## 8. Security & Permissions

### Authentication Flow (JWT)
Rail Django includes a full JWT implementation.

1.  **Login:**
    POST to `/api/auth/` (if configured) or your main endpoint:
    ```graphql
    mutation {
      login(username: "user", password: "pwd") {
        token
        refreshToken
        user { username }
      }
    }
    ```

2.  **Authenticate Requests:**
    Add header: `Authorization: Bearer <your_token>`

    If you use cookie-based JWTs, keep CSRF protection enabled and set:
    `JWT_ALLOW_COOKIE_AUTH=True`, `JWT_ENFORCE_CSRF=True`.

3.  **Refresh Token:**
    ```graphql
    mutation {
      refreshToken(refreshToken: "<refresh_token>") {
        token
      }
    }
    ```

### Role-Based Access Control (RBAC)
Define roles and assign them to users.

**Usage in Code:**
```python
from rail_django.security import require_role

@require_role("manager")
def resolve_financial_report(root, info):
    return generate_report()
```

### Field-Level Security
You can hide fields dynamically based on who is asking.

**Example: Masking Emails**
In `graphql_meta`:
```python
field_permissions={
    "email": {
        "roles": ["support"],
        "visibility": "masked",
        "mask_value": "user@***.com"
    }
}
```
A generic user will see `null` or receive a permission error. A support user sees the masked value. An admin sees the full value.

### Input Sanitization
The library automatically sanitizes inputs to prevent XSS. It strips dangerous tags (`<script>`, `<iframe>`) from string inputs before they reach your resolvers.

---

## 9. Extensions System

### Audit Logging
Tracks who did what.

**Events Logged:**
*   Login/Logout
*   Failed Login (Brute force detection)
*   Password Changes
*   Permission Denials

**Querying Logs:**
The logs are stored in `AuditEventModel`. You can build an admin dashboard using the built-in helper:
```python
from rail_django.extensions.audit import audit_logger
dashboard_data = audit_logger.get_security_report(hours=24)
```

### Data Exporting (Excel/CSV)
Don't write CSV writers manually. Use the export endpoint.

**Endpoint:** `POST /api/v1/export/`
**Payload:**
```json
{
    "app_name": "store",
    "model_name": "Product",
    "file_extension": "xlsx",
    "fields": [
        "name", 
        "category.name", 
        {"accessor": "price", "title": "Unit Price"}
    ],
    "max_rows": 10000,
    "variables": {"is_active": true}
}
```
This returns a binary stream of the generated Excel file.

Guardrails (allowlists, row caps, rate limiting) are configured via
`RAIL_DJANGO_EXPORT` in settings.

### Health Monitoring
Expose a health check for Kubernetes or Load Balancers.

**Query:**
```graphql
query {
  health {
    healthStatus {
      overallStatus # "healthy", "degraded", "unhealthy"
      components {
        databases { status message }
      }
      systemMetrics {
        cpuUsagePercent
        memoryUsagePercent
      }
    }
  }
}
```

### Multi-Factor Authentication (MFA)
Secure your high-value users.

1.  **Setup:**
    `setupTotp(deviceName: "My iPhone")` -> Returns QR Code URL.
2.  **Verify:**
    `verifyTotp(deviceId: 1, token: "123456")` -> Activates device.
3.  **Enforce:**
    Middleware checks `user.mfa_devices.exists()`. If enforced, it blocks other mutations until verified.

### PDF Templating Engine
Turn Django models into PDFs using HTML/CSS templates.

1.  **Create Template:** `templates/pdf/invoice.html`
2.  **Decorate Model:**
    ```python
    from rail_django.extensions.templating import model_pdf_template

    class Order(models.Model):
        @model_pdf_template(content="pdf/invoice.html")
        def download_invoice(self):
            return {"items": self.items.all()}
    ```
3.  **Download:** `GET /api/templates/store/order/download_invoice/<pk>/`

**Configuration (`RAIL_DJANGO_GRAPHQL_TEMPLATING`):**
Use CSS to style your PDFs (page size, margins).
```python
"default_template_config": {
    "page_size": "A4",
    "margin": "2cm",
    "font_family": "Helvetica"
}
```

---

## 10. Performance Tuning

### Query Optimization
The N+1 problem is the enemy of GraphQL.
Rail Django automatically uses `select_related` for ForeignKeys and `prefetch_related` for ManyToMany fields when you query nested data.

**Example:**
`query { products { category { name } } }`
The framework sees you asked for `category` and adds `.select_related('category')` to the underlying queryset automatically.

### DataLoader
For complex cases where auto-optimization fails (e.g. calculated properties or cross-service calls), enable DataLoaders in settings.
`"enable_dataloader": True`

### Performance Middleware
Enable request-level metrics with:
`GRAPHQL_PERFORMANCE_ENABLED=True`
Optional headers: `GRAPHQL_PERFORMANCE_HEADERS=True`

### Complexity Limiting
Prevent malicious users from crashing your server with massive queries.

**Settings:**
*   `max_query_depth`: 10 (e.g., `author { posts { author { posts ... } } }`)
*   `max_query_complexity`: 2000 points.
    *   Simple field = 1 point
    *   Relationship = 5 points
    *   List = 10 points * limit

---

## 11. Deployment & DevOps

### Docker Configuration
The project comes with a multi-stage `Dockerfile`.

**Structure:**
*   **Builder Stage:** Compiles Python dependencies and wheels.
*   **Final Stage:** Minimal slim image, copies wheels, installs runtime deps.

**Environment Variables:**
Ensure these are set in production (see `.env.example`):
*   `DJANGO_SECRET_KEY`: Must be random and secret.
*   `DJANGO_DEBUG`: **Must** be `False`.
*   `ALLOWED_HOSTS`: List of valid domains.
*   `DATABASE_URL`: Connection string for PostgreSQL.
*   Optional: `JWT_ALLOW_COOKIE_AUTH`, `JWT_ENFORCE_CSRF` (if using cookie auth).
*   Optional: `GRAPHQL_PERFORMANCE_ENABLED` (enable request metrics).
*   Optional: `EXPORT_MAX_ROWS`, `EXPORT_STREAM_CSV` (if wiring export guardrails).

### Production Checklist
1.  [ ] **HTTPS:** Ensure SSL is enabled (use Nginx or Load Balancer).
2.  [ ] **Secrets:** Move `.env` vars to a secure secret manager.
3.  [ ] **Static Files:** Ensure `collectstatic` runs during build/deploy.
4.  [ ] **Migrations:** Run `migrate` on release.
5.  [ ] **MFA:** Enforce MFA for staff users.
6.  [ ] **Logging:** Configure Sentry or similar for error tracking.

### Troubleshooting

**Error: "Signature has expired"**
*   **Cause:** JWT token is too old.
*   **Fix:** Use `refreshToken` mutation or login again. Check `JWT_ACCESS_TOKEN_LIFETIME`.

**Error: "Field 'xyz' not found"**
*   **Cause:** You might have excluded it in `graphql_meta` or `excluded_fields`.
*   **Fix:** Check permissions and visibility settings.

**Performance is slow**
*   **Check:** Are you querying a deep relationship without optimization?
*   **Fix:** Inspect SQL queries using `django-debug-toolbar` (in dev) or enable `log_performance` middleware.

---

## 12. Manual Deployment Guide

This guide explains how to manually deploy your `rail-django` application using the provided Docker and Nginx configurations, connecting to your external database machine.

### Prerequisites

1.  **Docker & Docker Compose** installed on the application server.
2.  **External Database**: A PostgreSQL database running on a separate machine, accessible from your application server.
3.  **Domain Name / Internal DNS**: Configured to point to your VM's IP address (e.g., `app.internal.corp`).

### 1. Environment Configuration

Copy the `.env.example` file to `.env` in your project root and update the variables:

```bash
cp .env.example .env
nano .env
```

**Key variables to set:**
- `DJANGO_DEBUG=False`
- `DJANGO_SECRET_KEY`: A long, random string.
- `DATABASE_URL`: Pointing to your external machine (e.g., `postgres://user:pass@192.168.1.50:5432/my_db`).
- `DJANGO_ALLOWED_HOSTS`: Your internal domain (e.g., `app.internal.corp`) or IP.
- `PGHOST`, `PGUSER`, `PGPASSWORD`: Required for the automatic backup service.

### 2. Deployment Steps

Run these commands from your project root:

#### A. Build and Start Services
This will build the Python image and start the Web, Nginx, and Backup containers.
```bash
docker-compose -f deploy/docker/docker-compose.yml up -d --build
```

#### B. Run Migrations
Apply database schema changes to your external database:
```bash
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py migrate
```

#### C. Collect Static Files
Prepare CSS, JS, and images for Nginx to serve:
```bash
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py collectstatic --no-input
```

#### D. Create Superuser (Optional)
```bash
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py createsuperuser
```

### 3. Directory Structure

- **`deploy/docker/`**: Contains the Dockerfile and Compose configuration.
- **`deploy/nginx/`**: Contains the Nginx reverse proxy configuration.
- **`backups/`**: Database backups will be stored here automatically every 24h (defined in `.env`).

### 4. Maintenance

#### Viewing Logs
```bash
docker-compose -f deploy/docker/docker-compose.yml logs -f
```

#### Stopping the Application
```bash
docker-compose -f deploy/docker/docker-compose.yml down
```

#### Updating the Application
1. Pull your latest code changes.
2. Re-run the build and migration steps:
```bash
docker-compose -f deploy/docker/docker-compose.yml up -d --build
docker-compose -f deploy/docker/docker-compose.yml exec web python manage.py migrate
```

### 5. Security Recommendations

1.  **SSL/TLS**: Mandatory. Use company-issued certificates or self-signed certs for internal traffic.
2.  **Firewall**: Configure `ufw` on your Ubuntu VM to allow traffic only from trusted internal subnets.
    ```bash
    ufw allow from 10.0.0.0/8 to any port 443
    ufw allow ssh
    ufw enable
    ```
3.  **Secrets**: Never commit your `.env` file to version control.
4.  **Updates**: Keep the VM OS updated (`apt update && apt upgrade`).

### 6. Setup HTTPS (Internal Network / Enterprise)

Since this server is inside a private company network, you cannot use standard Let's Encrypt challenges. You should use **Host Nginx** to handle SSL using certificates provided by your IT department.

#### Step 1: Adjust Docker Configuration
Move the Docker container to a private port so the Host Nginx can take over port 80/443.

1. Open `deploy/docker/docker-compose.yml`.
2. Change the `nginx` service ports:
   ```yaml
   nginx:
     # ...
     ports:
       - "127.0.0.1:8080:80"  # Bind to localhost port 8080
   ```
3. Restart your containers:
   ```bash
docker-compose -f deploy/docker/docker-compose.yml up -d --build
```

#### Step 2: Obtain Certificates
You have two options:

**Option A: Official Company Certificate (Recommended)**
Ask your IT/Security team for the SSL certificate for your internal domain (e.g., `app.corp.local`).
You need two files:
- `your_domain.crt` (The public certificate)
- `your_domain.key` (The private key)

**Option B: Self-Signed Certificate (For Testing)**
If you don't have an official cert, generate a self-signed one:
```bash
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/selfsigned.key \
  -out /etc/ssl/certs/selfsigned.crt
```

#### Step 3: Configure Host Nginx
Install Nginx on the VM:
```bash
sudo apt update
sudo apt install nginx
```

Create a secure configuration file:
```bash
sudo nano /etc/nginx/sites-available/my_internal_app
```

Paste this configuration (adjust paths and domain):

```nginx
server {
    listen 80;
    server_name app.internal.corp; # Your internal domain or IP
    return 301 https://$host$request_uri; # Force HTTPS
}

server {
    listen 443 ssl;
    server_name app.internal.corp;

    # Point to your certificates
    ssl_certificate /etc/ssl/certs/your_domain.crt;      # Or selfsigned.crt
    ssl_certificate_key /etc/ssl/private/your_domain.key; # Or selfsigned.key

    # SSL Settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://127.0.0.1:8080; # Points to Docker Container
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Step 4: Activate
```bash
sudo ln -s /etc/nginx/sites-available/my_internal_app /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

---

**Rail Django** - *Build faster, scale better.*
