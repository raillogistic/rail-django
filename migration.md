# Rail Django structure migration plan (library-only)

This plan assumes `rail_django` is a **library** and only ships scaffolding via `rail-admin startproject` / `startapp`. The checklist format is meant to be actionable and trackable.

## Target layout (library-only)

```
rail_django/
  __init__.py
  core/
  generators/
  introspection/
  security/
  validation/
  graphql/
    views/
  http/
    api/
    views/
    middleware/
    urls/
  extensions/
  integrations/
  config/
  scaffolding/
    project_template/
    app_template/
    app_template_minimal/
  management/commands/
  testing/
  utils/

tests/
```

---

## Phase 1 — Scaffolding separation (required)

### Checklist

- [x] Create new directories
  - [x] `rail_django/scaffolding`
  - [x] `rail_django/config`

- [x] Move scaffolding templates
  - [x] `rail_django/conf/project_template` -> `rail_django/scaffolding/project_template`
  - [x] `rail_django/conf/app_template` -> `rail_django/scaffolding/app_template`
  - [x] `rail_django/conf/app_template_minimal` -> `rail_django/scaffolding/app_template_minimal`

- [x] Move settings files into config namespace
  - [x] `rail_django/conf/framework_settings.py` -> `rail_django/config/framework_settings.py`
  - [x] `rail_django/conf/test_settings.py` -> `rail_django/config/test_settings.py`

- [x] Optional cleanup
  - [x] Remove `rail_django/conf/__init__.py`
  - [x] Remove `rail_django/conf/`

### Import/path updates

- [x] `rail_django/bin/rail_admin.py`
  - [x] Update template path to `rail_django/scaffolding/project_template`
  - [x] Prefer `importlib.resources` to resolve template dirs

- [x] `rail_django/management/commands/startapp.py`
  - [x] Update template path to `rail_django/scaffolding/app_template`
  - [x] Update template path to `rail_django/scaffolding/app_template_minimal`

- [x] `pyproject.toml`
  - [x] `DJANGO_SETTINGS_MODULE = "rail_django.config.test_settings"`

- [x] Docs/config references
  - [x] Replace `rail_django.conf.framework_settings` -> `rail_django.config.framework_settings`
  - [x] Replace `rail_django.conf.test_settings` -> `rail_django.config.test_settings`

- [x] Packaging
  - [x] `MANIFEST.in`: replace `recursive-include rail_django/conf *` with:
    - [x] `recursive-include rail_django/scaffolding *`
    - [x] `recursive-include rail_django/config *`

---

## Phase 2 — GraphQL view consolidation (required)

Two overlapping locations exist: `rail_django/views/graphql` and `rail_django/views/graphql_views`.

### Checklist

- [x] Create new directory
  - [x] `rail_django/graphql/views`

- [x] Move GraphQL view modules (recommended canonical source: `views/graphql`)
  - [x] Move `rail_django/views/graphql/*` -> `rail_django/graphql/views/`
  - [x] Move `rail_django/views/graphql_views/multi_schema/*` -> `rail_django/graphql/views/multi_schema/`

- [x] Remove old directories (shims removed)
  - [x] Remove `rail_django/views/graphql/`
  - [x] Remove `rail_django/views/graphql_views/`

### Import updates

- [x] Update imports in moved modules to new package location
- [x] Update external imports
  - [x] `rail_django/urls.py`: `from .views.graphql_views import ...` -> `from .graphql.views import ...`
  - [x] Tests: `tests/integration/test_multi_schema.py`
  - [x] Any patch paths referencing `rail_django.views.graphql_views.*`

### Backward compatibility (removed)

- [x] Remove shims in old locations (no legacy GraphQL view paths kept)

---

## Phase 3 — HTTP/API consolidation (recommended)

### Checklist

- [x] Create new directories
  - [x] `rail_django/http/api`
  - [x] `rail_django/http/views`
  - [x] `rail_django/http/urls`

- [x] Move API package
  - [x] `rail_django/api/*` -> `rail_django/http/api/`

- [x] Move view modules
  - [x] `rail_django/views/health_views.py` -> `rail_django/http/views/health.py`
  - [x] `rail_django/views/audit_views.py` -> `rail_django/http/views/audit.py`

- [x] Move URL helper modules
  - [x] `rail_django/health_urls.py` -> `rail_django/http/urls/health.py`
  - [x] `rail_django/audit_urls.py` -> `rail_django/http/urls/audit.py`

### Import updates

- [x] `rail_django/urls.py`
  - [x] Update `include("rail_django.api.urls"...)` -> `include("rail_django.http.api.urls"...)`
  - [x] Update health/audit url imports
  - [x] Update GraphQL view import to new package (Phase 2)

- [x] Tests
  - [x] `tests/test_health_system.py` patch paths
  - [x] `tests/unit/test_audit_views.py` patch paths

### Backward compatibility (removed)

- [x] Remove legacy shims in `rail_django/api/`, `rail_django/health_urls.py`, `rail_django/audit_urls.py`, `rail_django/views/*_views.py`

---

## Phase 4 — Tests layout (optional but recommended)

### Checklist

- [x] Merge test roots
  - [x] `rail_django/tests/unit` -> `tests/unit`
  - [x] `rail_django/tests/integration` -> `tests/integration`
  - [x] `rail_django/tests/test_health_system.py` -> `tests/test_health_system.py`
  - [x] Remove `rail_django/tests/`

- [x] Update references in docs/CI
  - [x] Any references to `rail_django.tests.*` updated to `tests.*`

---

## Phase 5 — Repository hygiene (optional)

### Checklist

- [x] Move example apps under `examples/`
  - [x] `test_app/` -> `examples/test_app/`

- [x] Ignore dev artifacts
  - [x] `.gitignore`: add `*.xlsx`, `.tmp/`

---

## Phase 6 — Documentation updates (required)

### Checklist

- [x] Update configuration references in docs and meta docs
  - [x] `AGENTS.md`: `rail_django.conf.framework_settings` -> `rail_django.config.framework_settings`
  - [x] `CLAUDE.md`: `rail_django.conf.framework_settings` -> `rail_django.config.framework_settings`
  - [x] `GEMINI.md`: `rail_django.conf.framework_settings` -> `rail_django.config.framework_settings`
  - [x] `CLAUDE.md` / `GEMINI.md`: update `rail_django.conf.test_settings` -> `rail_django.config.test_settings`

- [x] Update docs in templates (scaffolding)
  - [x] `rail_django/scaffolding/project_template/USAGE.md` (no updates needed)
  - [x] `rail_django/scaffolding/project_template/docs/**`

- [x] Update `docs/` in repo
  - [x] Search/replace `rail_django.conf.*` -> `rail_django.config.*`
  - [x] Update any paths referencing `rail_django/conf/...` -> `rail_django/scaffolding/...`
  - [x] Update GraphQL view paths if mentioned (`rail_django.views.graphql_views.*` -> `rail_django.graphql.views.*`)
  - [x] Update API path references if mentioned (`rail_django.api.*` -> `rail_django.http.api.*`)
  - [x] Update audit view references (`rail_django.views.audit_views` -> `rail_django.http.views.audit`)
  - [x] Update health URLs references (`rail_django.health_urls` -> `rail_django.http.urls.health`)

---

## Import/path change summary

- `rail_django.conf.project_template` -> `rail_django.scaffolding.project_template`
- `rail_django.conf.app_template` -> `rail_django.scaffolding.app_template`
- `rail_django.conf.app_template_minimal` -> `rail_django.scaffolding.app_template_minimal`
- `rail_django.conf.framework_settings` -> `rail_django.config.framework_settings`
- `rail_django.conf.test_settings` -> `rail_django.config.test_settings`
- `rail_django.views.graphql_views.*` -> `rail_django.graphql.views.*`
- `rail_django.api.*` -> `rail_django.http.api.*`
- `rail_django.views.health_views` -> `rail_django.http.views.health`
- `rail_django.views.audit_views` -> `rail_django.http.views.audit`
- `rail_django.health_urls` -> `rail_django.http.urls.health`
- `rail_django.audit_urls` -> `rail_django.http.urls.audit`

---

## Verification checklist

- [ ] `rail-admin startproject my_project` works and renders templates with `-tpl` cleanup.
- [ ] `python -m pytest -m unit` passes.
- [ ] Django test runner works with updated `DJANGO_SETTINGS_MODULE`.
- [ ] `rail_django/urls.py` imports resolve.
- [ ] `MANIFEST.in` includes scaffolding and config files.

