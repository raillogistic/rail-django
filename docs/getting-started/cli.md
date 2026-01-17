# CLI and Management Commands

Rail Django provides a small CLI wrapper and several management commands.

## rail-admin

`rail-admin` wraps Django's `execute_from_command_line` to use the
Rail Django project template.

Example:

```bash
rail-admin startproject my_api
```

This injects the template under `rail_django/conf/project_template` and
renames `*.py-tpl` files after generation.

## Management commands

Available commands in `rail_django.management.commands`:

- `startapp`: project scaffolding with Rail Django defaults (includes a `meta.yaml` stub)
- `setup_security`: create default RBAC groups and permissions
- `security_check`: run security validation checks
- `manage_schema_versions`: inspect or update schema versions
- `run_performance_benchmarks`: execute performance benchmarks
- `health_monitor`: run health checks from the CLI

Run with:

```bash
python manage.py <command>
```
