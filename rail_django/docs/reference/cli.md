# CLI Reference

Rail Django includes a command-line tool `rail-admin` and several custom Django management commands to help you develop, secure, and monitor your application.

## `rail-admin`

The `rail-admin` tool is the entry point for scaffolding new projects. It wraps `django-admin` but uses the Rail Django project template by default.

### `startproject`

Creates a new Rail Django project with the recommended directory structure, security settings, and GraphQL configuration.

```bash
rail-admin startproject <project_name> [destination]
```

**Arguments:**

*   `project_name`: Name of the project (and the python package).
*   `destination` (optional): Directory to create the project in. Defaults to a directory named `<project_name>`.

**Example:**

```bash
# Create a new project in the current directory
rail-admin startproject my_api .
```

---

## Management Commands

Rail Django provides several custom management commands. Run these using `python manage.py <command>`.

### `startapp`

A custom version of Django's `startapp` that creates an app structure optimized for Rail Django (including `schemas.py` and `graphql/` directories).

```bash
python manage.py startapp <app_name> [options]
```

**Options:**

*   `--minimal`: Create a stripped-down app structure (omits standard Django views/admin if you only need GraphQL).

### `security_check`

Audits your current configuration for security vulnerabilities and best practices.

```bash
python manage.py security_check [options]
```

**Options:**

*   `--fix`: Attempt to automatically fix common configuration issues.
*   `--verbose`: Display detailed output for every check performed.
*   `--format`: Output format, `text` (default) or `json`.

### `setup_security`

Interactive or automated setup of advanced security features like MFA, Audit Logging, and Rate Limiting.

```bash
python manage.py setup_security [options]
```

**Options:**

*   `--enable-mfa`: Configure Multi-Factor Authentication.
*   `--enable-audit`: Enable audit logging (default: True).
*   `--create-settings`: Generate a `security_settings.py` file.
*   `--migrate`: Automatically run database migrations for security tables.
*   `--force`: Overwrite existing security configuration files.

### `audit_management`

Manage security and compliance audit logs, including export and cleanup.

```bash
python manage.py audit_management <subcommand> [options]
```

**Subcommands:**

*   **`export`**: Export logs to a file.
    *   `--output <file>`: (Required) Path to the output file.
    *   `--format <fmt>`: Output format, `json` (default) or `csv`.
    *   `--days <n>`: Export logs from the last N days (default: 30).
*   **`cleanup`**: Delete old logs to free up space.
    *   `--days <n>`: (Required) Delete logs older than N days.
    *   `--dry-run`: Show what would be deleted without executing.
*   **`summary`**: Show a quick security summary.
    *   `--hours <n>`: Show summary for the last N hours (default: 24).

### `health_monitor`

Run continuous health monitoring of the GraphQL system with optional alerting.

```bash
python manage.py health_monitor [options]
```

**Options:**

*   `--summary-only`: Perform a single check, display the report, and exit.
*   `--duration <min>`: Run monitoring for N minutes (runs indefinitely if omitted).
*   `--interval <sec>`: Time between checks in seconds (default: 60).
*   `--enable-alerts`: Enable email alerts (requires email settings).
*   `--alert-recipients`: Space-separated list of email addresses.
*   `--config-file <path>`: Path to a JSON configuration file defining check thresholds.

### `run_performance_benchmarks`

Execute performance tests to detect N+1 issues, verify caching, and check load capacity.

```bash
python manage.py run_performance_benchmarks [options]
```

**Options:**

*   `--test <type>`: Test to run (`n_plus_one`, `caching`, `load`, `complexity`, or `all`).
*   `--output-dir <path>`: Directory for results (default: `benchmark_results`).
*   `--verbose`: Display detailed performance metrics.
*   `--data-sizes`: Comma-separated list of sizes for N+1 tests (default: `10,50,100`).
*   `--concurrent-users`: Users for load tests (default: `1,5,10`).

### `render_pdf`

Render a registered PDF template to a file using the framework's templating system.

```bash
python manage.py render_pdf <template_path> --pk <id> [options]
```

**Arguments:**

*   `template_path`: The URL path/key of the registered template.

**Options:**

*   `--pk <id>`: (Required) The Primary Key of the model instance to render.
*   `--output <file>` / `-o`: Output file path.
*   `--client-data <json>`: Optional JSON string for custom data injection.
*   `--html`: Render an HTML preview instead of a PDF.
