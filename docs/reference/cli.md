# CLI Reference

Rail Django includes a command-line tool `rail-admin` which wraps `django-admin` with framework-specific defaults.

## `rail-admin startproject`

Creates a new Rail Django project with the recommended directory structure.

```bash
rail-admin startproject <project_name> [destination]
```

### Arguments

*   `project_name`: Name of the project (and the python package).
*   `destination` (optional): Directory to create the project in.

### Options

*   `--template`: Specify a custom project template.
*   `--extension`: File extensions to render.

### Example

```bash
rail-admin startproject my_api .
```

## Management Commands

Rail Django also adds several Django management commands.

*   `python manage.py graphql_schema`: Dump the schema to a file (JSON/SDL).
