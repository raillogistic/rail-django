# Installation

## Prerequisites

- **Python** 3.11 or higher
- **pip** (Python Package Installer)
- **PostgreSQL** (recommended for production)
- **Redis** (optional, for cache and rate limiting)
- **Docker & Docker Compose** (optional, for containerized development)

---

## Package Installation

### From PyPI

```bash
pip install rail-django
```

### From GitHub

```bash
pip install git+https://github.com/raillogistic/rail-django.git
```

### Development Mode Installation

To contribute to the framework:

```bash
git clone https://github.com/raillogistic/rail-django.git
cd rail-django
pip install -e .
```

---

## Creating a New Project

### Using rail-admin

The `rail-admin` CLI automatically creates the recommended project structure:

```bash
rail-admin startproject my_project
cd my_project
```

### Created Structure

```
my_project/
├── manage.py           # Django entry point
├── root/               # Main configuration
│   ├── __init__.py
│   ├── settings/       # Settings (base, dev, prod)
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── production.py
│   ├── urls.py         # Global routing
│   ├── wsgi.py         # WSGI (production)
│   ├── asgi.py         # ASGI (WebSocket)
│   └── webhooks.py     # Webhook configuration
├── apps/               # Your Django applications
├── requirements/       # Dependencies
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── docs/               # Documentation
├── deploy/             # Deployment configuration
├── .env.example        # Environment variables
└── Dockerfile          # Docker build
```

---

## Installing Dependencies

### Development

```bash
pip install -r requirements/dev.txt
```

### Production

```bash
pip install -r requirements/prod.txt
```

---

## Database Configuration

### SQLite (Development)

By default, the project uses SQLite (no configuration required).

### PostgreSQL (Production)

1. Create the database:

```bash
createdb my_project_db
```

2. Configure the environment variable:

```bash
export DATABASE_URL=postgres://user:password@localhost:5432/my_project_db
```

3. Or modify `.env`:

```ini
DATABASE_URL=postgres://user:password@localhost:5432/my_project_db
```

---

## Initialization

### Apply Migrations

```bash
python manage.py migrate
```

### Create a Superuser

```bash
python manage.py createsuperuser
```

### Start the Server

```bash
python manage.py runserver
```

Access:

- **GraphiQL**: http://localhost:8000/graphql/graphiql/
- **Django Admin**: http://localhost:8000/admin/

---

## Verifying Installation

### GraphQL Test

Open GraphiQL and execute:

```graphql
query {
  __schema {
    types {
      name
    }
  }
}
```

### Authentication Test

```graphql
mutation {
  login(username: "admin", password: "your_password") {
    ok
    token
    user {
      username
    }
  }
}
```

---

## Next Steps

- [Quickstart](./quickstart.md) - Create your first API
- [Configuration](../graphql/configuration.md) - Customize the framework

---

## Troubleshooting

### Error: "rail-admin command not found"

Make sure the package is installed and that the Scripts/bin directory is in your PATH.

```bash
pip show rail-django
# Check "Location" and add bin/ to your PATH
```

### Error: "No module named 'rail_django'"

Verify the installation:

```bash
pip list | grep rail
```

If absent, reinstall:

```bash
pip install rail-django
```

### Migration Error

Make sure the database is accessible and that `DATABASE_URL` is correct.

```bash
python manage.py dbshell
```
