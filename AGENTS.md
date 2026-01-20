# Repository Guidelines

## Project Structure & Module Organization
- `rail_django/`: library code. Key areas: `core/` (schema registry/build), `generators/` (type/query/mutation generation), `security/` (RBAC, input validation), `extensions/` (health, audit, export), `api/` and `views/` (HTTP endpoints), `middleware/`, and `management/`.
- `rail_django/tests/unit/` and `rail_django/tests/integration/`, plus `rail_django/tests/test_health_system.py` for cross-cutting health checks.
- `rail_django/conf/`: project/app templates and framework settings used by the CLI scaffolder.
- `docs/`: contributor reference (`docs/architecture.md`, `docs/modules.md`, `docs/security.md`, `docs/testing.md`).

## Build, Test, and Development Commands
- `python -m pip install -r rail_django/conf/project_template/requirements/base.txt-tpl` Install runtime dependencies (single source of truth).
- `python -m pip install black` Install formatter for local development.
- `python -m pip install -e .` Editable install of the package for local development.
- `rail-admin startproject my_api` Scaffold a sample project from `rail_django/conf/project_template`.
- `python manage.py runserver` Run a generated project locally.
- `pytest -m unit` Run fast unit tests; `pytest -m integration` runs DB-backed tests.
- `DJANGO_SETTINGS_MODULE=rail_django.conf.framework_settings python -m django test rail_django.tests.unit` Run the Django test runner (CI path).
- `python -m black --check rail_django/testing rail_django/tests/unit/test_phase0_regressions.py` Formatting check used in CI.

## Coding Style & Naming Conventions
- Python uses 4-space indentation and standard PEP 8 naming: `snake_case` for modules/functions, `PascalCase` for classes.
- Tests follow `test_*.py` and `test_*` function naming under `rail_django/tests/`.
- GraphQL fields are camelCase by default (`auto_camelcase = True`); note this when adding schema fields.

## Testing Guidelines
- Use pytest markers: `@pytest.mark.unit` and `@pytest.mark.integration`.
- Prefer `rail_django.testing` helpers (`build_schema`, `RailGraphQLTestClient`) for isolated schema tests.
- Focus coverage on schema generation, security controls, and error handling as described in `docs/testing.md`.

## Documentation Guidelines
- Documentation should always be written in plain English.

## Commit & Pull Request Guidelines
- Recent commits use short, descriptive summaries (often imperative or terse). Keep the first line concise; add a body for complex changes.
- No PR template is defined. Include a clear description, tests run, and any docs/config changes. Link related issues when applicable.

## Security & Configuration Tips
- Configuration is documented in `docs/configuration.md` and `docs/security.md`; align code changes with those settings.
- When changing auth, RBAC, or input validation flows, update the relevant docs and add regression coverage.
