# Rail-Django Upgrade Plan

## 1. Packaging Modernization (Migration to `pyproject.toml`)

We will move from `setup.py` to a standard `pyproject.toml` (PEP 621) configuration.

**Why?**
- Standard Python packaging practice.
- Better tool compatibility (poetry, hatch, ruff, black).
- Simplifies dependency management.

**Plan:**
1.  Create `pyproject.toml`.
2.  Port metadata from `setup.py` (name, version, authors, classifiers).
3.  Port `install_requires` to `dependencies`.
4.  Port `extras_require` to `optional-dependencies`.
5.  Port `console_scripts` entry points to `[project.scripts]`.
6.  Configure `setuptools` specific settings in `[tool.setuptools]`.
7.  Replace `setup.py` with a minimal stub or remove it entirely (if editable installs work fine without it).

**Draft `pyproject.toml`:**

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "rail-django"
version = "1.1.4"
description = "A Django wrapper framework with pre-configured settings and tools."
readme = "README.md"
authors = [
  { name = "Milia Khaled", email = "miliakhaled@gmail.com" },
]
license = { text = "MIT" }
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Framework :: Django",
    "Framework :: Django :: 5.0",
    "Programming Language :: Python :: 3.11",
]
dependencies = [
    "Django>=5.0",
    "graphene-django>=3.1.5",
    "graphql-relay>=3.2.0",
    "django-filter>=23.2",
    # ... other deps
]
requires-python = ">=3.11"

[project.optional-dependencies]
subscriptions = [
    "channels>=4.0.0",
    "daphne>=4.0.0",
]

[project.scripts]
rail-admin = "rail_django.bin.rail_admin:main"

[tool.setuptools.packages.find]
include = ["rail_django*"]
```

## 2. Django 5.0 & Async Compatibility

**Why?**
- Django 5.0 introduces `GeneratedField` and more async capabilities.
- We must ensure `AutoSchemaGenerator` doesn't break on new field types.

**Risks:**
- `GeneratedField`: Graphene-Django might not map this automatically. We may need to add a converter in `rail_django/generators/types`.
- `Async`: Graphene-Django has `async` support, but our custom middleware and resolvers in `rail_django` need to be audit-checked for `async/await` correctness if we enable async views.

**Plan:**
1.  **Test GeneratedField:** Create a test model with `models.GeneratedField` and verify if `AutoSchemaGenerator` crashes or ignores it.
    - *Fix:* Register a converter if needed.
2.  **Async Resolver Audit:** Review `rail_django/core/schema/auto_generator.py` and resolvers. ensure we aren't blocking the event loop if the user switches to `AsyncGraphQLView`.

## 3. Tooling Enhancements ("Eject" & Export)

**Why?**
- The "magic" of `AutoSchemaGenerator` hides the schema details.
- Users need to see the generated SDL (Schema Definition Language) for debugging or for frontend code generation.

**Plan:**
1.  **Add `export_schema` command:**
    - Use `graphene-django`'s management command logic as a base.
    - Add a `rail-admin eject-schema` or `python manage.py rail_export_schema` command.
    - It should load the `AutoSchemaGenerator`, build the schema, and print `schema.graphql`.
2.  **Introspection Support:**
    - Ensure `rail-django` projects are configured to allow introspection by default in DEV mode.

## 4. Documentation

- Add a new section `Customizing Generated Types` in `docs/` explaining how to extend the auto-generated types manually.
