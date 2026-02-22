"""Unit tests for scaffolded deployment templates."""

from importlib import resources

import pytest

pytestmark = pytest.mark.unit


def _project_template_file(*relative_parts: str) -> str:
    return resources.files("rail_django").joinpath(
        "scaffolding", "project_template", *relative_parts
    ).read_text(encoding="utf-8")


def test_env_example_disables_startup_migrations_and_collectstatic() -> None:
    text = _project_template_file(".env.example")

    assert "RUN_MIGRATIONS=False" in text
    assert "RUN_COLLECTSTATIC=False" in text


def test_env_example_sets_asgi_runtime_defaults() -> None:
    text = _project_template_file(".env.example")

    assert "DJANGO_SERVER_MODE=asgi" in text
    assert "DJANGO_ASGI_MODULE=root.asgi:application" in text
    assert "ASGI_BIND=0.0.0.0" in text
    assert "ASGI_PORT=8000" in text


def test_entrypoint_defaults_to_asgi_server_with_wsgi_fallback() -> None:
    text = _project_template_file("deploy", "docker", "entrypoint.sh")

    assert 'SERVER_MODE=${DJANGO_SERVER_MODE:-asgi}' in text
    assert 'if [ "$SERVER_MODE" = "wsgi" ]; then' in text
    assert "exec daphne \\" in text


def test_backup_script_does_not_use_pipeline_success_for_pg_dump() -> None:
    text = _project_template_file("deploy", "docker", "backup.sh")

    assert 'pg_dump --dbname="$DATABASE_URL" > "$RAW_FILE"' in text
    assert "| gzip >" not in text


def test_compose_healthcheck_uses_http_readiness_probe() -> None:
    text = _project_template_file("deploy", "docker", "docker-compose.yml")

    assert "/health/ready/" in text
    assert "socket.socket()" not in text


def test_production_template_disables_graphiql_and_introspection_by_default() -> None:
    text = _project_template_file("root", "settings", "production.py-tpl")

    assert (
        "ENABLE_PROD_GRAPHIQL = env.bool('RAIL_ENABLE_PROD_GRAPHIQL', default=False)"
        in text
    )
    assert (
        "ENABLE_PROD_INTROSPECTION = env.bool('RAIL_ENABLE_PROD_INTROSPECTION', default=False)"
        in text
    )
    assert 'schema_config["schema_settings"]["enable_graphiql"] = False' in text
    assert 'schema_config["schema_settings"]["enable_introspection"] = False' in text
