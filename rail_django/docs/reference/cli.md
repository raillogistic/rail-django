# CLI reference

Rail Django provides `rail-admin` plus Django management commands for
scaffolding, security operations, schema export, and extension workflows.
This reference reflects commands currently present in the repository.

## `rail-admin`

Use `rail-admin` as a `django-admin` wrapper that injects Rail Django project
templates.

### `startproject`

Create a project from the Rail Django template.

```bash
rail-admin startproject <project_name> [destination]
```

When you do not pass custom template flags, `rail-admin` adds the framework
project template automatically and performs post-processing for template files.

## Core management commands

Run commands with `python manage.py <command>`.

### `startapp`

Create an app with Rail Django scaffolding.

```bash
python manage.py startapp <app_name> [options]
```

Options:

- `--minimal`: Use the minimal app template.

### `security_check`

Check security configuration and output recommendations.

```bash
python manage.py security_check [options]
```

Options:

- `--fix`
- `--verbose`
- `--format text|json`

### `setup_security`

Generate and apply security setup helpers.

```bash
python manage.py setup_security [options]
```

Options:

- `--enable-mfa`
- `--enable-audit`
- `--create-settings`
- `--settings-file <path>`
- `--migrate`
- `--force`

### `audit_management`

Export, clean up, or summarize audit events.

```bash
python manage.py audit_management <action> [options]
```

Actions:

- `export --format json|csv --days <n> --output <file>`
- `cleanup --days <n> [--dry-run]`
- `summary --hours <n>`

### `health_monitor`

Run one-time or continuous health monitoring.

```bash
python manage.py health_monitor [options]
```

Options:

- `--summary-only`
- `--duration <minutes>`
- `--interval <seconds>`
- `--config-file <json-path>`
- `--enable-alerts`
- `--alert-recipients <email ...>`

### `run_performance_benchmarks`

Run performance benchmark suites.

```bash
python manage.py run_performance_benchmarks [options]
```

Options:

- `--test n_plus_one|caching|load|complexity|all`
- `--output-dir <path>`
- `--data-sizes <csv>`
- `--concurrent-users <csv>`
- `--requests-per-user <int>`
- `--query-depths <csv>`
- `--cache-scenarios <csv>`
- `--verbose`
- `--no-cleanup`

### `render_pdf`

Render a registered template to PDF or HTML.

```bash
python manage.py render_pdf <template_path> --pk <id> [options]
```

Options:

- `--output, -o <path>`
- `--client-data <json>`
- `--html`

### `eject_schema`

Export GraphQL schema as SDL or introspection JSON.

```bash
python manage.py eject_schema [options]
```

Options:

- `--out <path>`
- `--json`
- `--indent <int>`

### `bump_metadata_deploy_version`

Bump metadata deployment version values.

```bash
python manage.py bump_metadata_deploy_version [options]
```

Options:

- `--key <name>`
- `--value <value>`

### `manage_schema_versions`

This command exists but intentionally raises an error because schema versioning
was removed.

```bash
python manage.py manage_schema_versions
```

## Form extension commands

When the form extension command modules are available in your project, you can
use these commands:

- `python manage.py export_form_schema --app <label> --model <name> [--out <file>]`
- `python manage.py generate_form_types --app <label> --model <name> [--out <file>]`

## Next steps

For project setup flows, continue with
[installation](../getting-started/installation.md) and
[quickstart](../getting-started/quickstart.md).
