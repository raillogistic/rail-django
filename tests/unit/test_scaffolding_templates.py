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


def test_env_example_uses_non_default_secret_placeholders() -> None:
    text = _project_template_file(".env.example")

    assert "DJANGO_SECRET_KEY=REPLACE_WITH_LONG_RANDOM_SECRET_KEY" in text
    assert "DJANGO_SUPERUSER_PASSWORD=REPLACE_WITH_STRONG_PASSWORD" in text
    assert "change_me_in_production_with_a_long_random_string" not in text
    assert "DJANGO_SUPERUSER_PASSWORD=change_me" not in text


def test_env_example_sets_asgi_runtime_defaults() -> None:
    text = _project_template_file(".env.example")

    assert "DJANGO_SERVER_MODE=asgi" in text
    assert "DJANGO_ASGI_MODULE=root.asgi:application" in text
    assert "ASGI_BIND=0.0.0.0" in text
    assert "ASGI_PORT=8000" in text


def test_env_example_exposes_backup_postgres_image_override() -> None:
    text = _project_template_file(".env.example")

    assert "BACKUP_POSTGRES_IMAGE=postgres:16-alpine" in text


def test_entrypoint_defaults_to_asgi_server_with_wsgi_fallback() -> None:
    text = _project_template_file("deploy", "docker", "entrypoint.sh")

    assert 'SERVER_MODE=${DJANGO_SERVER_MODE:-asgi}' in text
    assert 'if [ "$SERVER_MODE" = "wsgi" ]; then' in text
    assert "exec daphne \\" in text


def test_backup_script_does_not_use_pipeline_success_for_pg_dump() -> None:
    text = _project_template_file("deploy", "docker", "backup.sh")

    assert 'pg_dump --dbname="$DATABASE_URL" > "$RAW_FILE"' in text
    assert "| gzip >" not in text


def test_backup_script_checks_pg_dump_major_against_server_major() -> None:
    text = _project_template_file("deploy", "docker", "backup.sh")

    assert "SHOW server_version_num;" in text
    assert "pg_dump major version (" in text
    assert "BACKUP_POSTGRES_IMAGE" in text


def test_compose_healthcheck_uses_http_readiness_probe() -> None:
    text = _project_template_file("deploy", "docker", "docker-compose.yml")

    assert "/health/ready/" in text
    assert "socket.socket()" not in text


def test_compose_backup_image_is_configurable_for_server_compatibility() -> None:
    text = _project_template_file("deploy", "docker", "docker-compose.yml")

    assert "image: ${BACKUP_POSTGRES_IMAGE:-postgres:16-alpine}" in text


def test_compose_mounts_cache_directory_for_shared_runtime_cache() -> None:
    text = _project_template_file("deploy", "docker", "docker-compose.yml")

    assert "${CACHE_PATH:-../../cache}:/home/app/web/cache" in text


def test_deploy_script_runs_schema_tasks_before_up() -> None:
    text = _project_template_file("deploy", "deploy.sh")

    migrate_cmd = 'run --rm --entrypoint python web manage.py migrate'
    up_cmd = '"${COMPOSE[@]}" -f "$COMPOSE_FILE" up -d'
    collectstatic_cmd = (
        'run --rm --entrypoint python web manage.py collectstatic --noinput'
    )

    assert migrate_cmd in text
    assert collectstatic_cmd in text
    assert up_cmd in text
    assert text.index(migrate_cmd) < text.index(up_cmd)
    assert text.index(collectstatic_cmd) < text.index(up_cmd)


def test_deploy_script_validates_runtime_storage_before_schema_tasks() -> None:
    text = _project_template_file("deploy", "deploy.sh")

    validation_step = 'note "Validating runtime storage permissions..."'
    migrate_cmd = 'run --rm --entrypoint python web manage.py migrate'

    assert "ensure_runtime_mount_writable" in text
    assert "/home/app/web/mediafiles" in text
    assert "/home/app/web/logs" in text
    assert "/home/app/web/cache" in text
    assert validation_step in text
    assert text.index(validation_step) < text.index(migrate_cmd)


def test_deploy_script_waits_for_http_readiness_probe() -> None:
    text = _project_template_file("deploy", "deploy.sh")

    assert "http://127.0.0.1:8000/health/ready/" in text
    assert "print('ready')" not in text


def test_deploy_script_non_interactive_superuser_is_idempotent() -> None:
    text = _project_template_file("deploy", "deploy.sh")

    assert "Ensuring superuser exists (non-interactive)" in text
    assert "get_or_create" in text
    assert "check_password" in text


def test_deploy_script_ensures_cache_directory_exists() -> None:
    text = _project_template_file("deploy", "deploy.sh")

    assert 'cache_path="$(read_env CACHE_PATH)"' in text
    assert 'ensure_dir "$SCRIPT_DIR/docker/$cache_path"' in text


def test_deploy_script_rejects_placeholder_secret_values() -> None:
    text = _project_template_file("deploy", "deploy.sh")

    assert 'if is_insecure_secret "$secret_key"; then' in text
    assert "DJANGO_SECRET_KEY appears to use a placeholder" in text
    assert 'if is_insecure_secret "$su_password"; then' in text
    assert "DJANGO_SUPERUSER_PASSWORD appears to use a placeholder" in text


def test_project_template_gitignore_covers_runtime_artifacts() -> None:
    text = _project_template_file(".gitignore")

    assert "media/" in text
    assert "backups/" in text
    assert "cache/" in text


def test_project_template_dockerignore_excludes_tls_key_material() -> None:
    text = _project_template_file(".dockerignore")

    assert "deploy/nginx/certs/*.crt" in text
    assert "deploy/nginx/certs/*.key" in text


def test_nginx_template_restricts_sensitive_health_diagnostics() -> None:
    text = _project_template_file("deploy", "nginx", "default.conf")

    assert "location ~ ^/health/(api|metrics|components|history)/?$ {" in text
    assert "location ~ ^/api/v1/health/?$ {" in text
    assert "allow 127.0.0.1;" in text
    assert "deny all;" in text


def test_deploy_usage_manual_steps_run_schema_tasks_before_starting_services() -> None:
    text = _project_template_file("deploy", "USAGE.md")

    build_cmd = "docker-compose -f deploy/docker/docker-compose.yml build web"
    migrate_cmd = (
        "docker-compose -f deploy/docker/docker-compose.yml run --rm "
        "--entrypoint python web manage.py migrate"
    )
    collectstatic_cmd = (
        "docker-compose -f deploy/docker/docker-compose.yml run --rm "
        "--entrypoint python web manage.py collectstatic --no-input"
    )
    up_cmd = "docker-compose -f deploy/docker/docker-compose.yml up -d"

    assert build_cmd in text
    assert migrate_cmd in text
    assert collectstatic_cmd in text
    assert up_cmd in text
    assert text.index(build_cmd) < text.index(migrate_cmd)
    assert text.index(migrate_cmd) < text.index(collectstatic_cmd)
    assert text.index(collectstatic_cmd) < text.index(up_cmd)


def test_runtime_dockerfile_excludes_dev_editors_and_libffi_dev() -> None:
    text = _project_template_file("deploy", "docker", "Dockerfile")

    assert "libffi8" in text
    assert "libffi-dev" not in text
    assert "vim nano" not in text
    assert "--no-deps -r requirements/rail-django.txt" not in text


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


def test_production_template_adds_graphql_security_middleware_after_auth() -> None:
    text = _project_template_file("root", "settings", "production.py-tpl")

    assert "rail_django.middleware.auth.GraphQLAuthenticationMiddleware" in text
    assert "rail_django.middleware.auth.GraphQLRateLimitMiddleware" in text
    assert '_auth_middleware = "django.contrib.auth.middleware.AuthenticationMiddleware"' in text
    assert "MIDDLEWARE.insert(_insert_at, mw)" in text
