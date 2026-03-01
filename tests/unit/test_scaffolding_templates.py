"""Unit tests for scaffolded deployment templates."""

from importlib import resources

import pytest

pytestmark = pytest.mark.unit


def _project_template_file(*relative_parts: str) -> str:
    return resources.files("rail_django").joinpath(
        "scaffolding", "project_template", *relative_parts
    ).read_text(encoding="utf-8")


def _project_template_path(*relative_parts: str):
    return resources.files("rail_django").joinpath(
        "scaffolding", "project_template", *relative_parts
    )


def _rail_django_file(*relative_parts: str) -> str:
    return resources.files("rail_django").joinpath(*relative_parts).read_text(
        encoding="utf-8"
    )


def test_env_prod_disables_startup_migrations_and_collectstatic() -> None:
    text = _project_template_file(".env.prod-tpl")

    assert "RUN_MIGRATIONS=False" in text
    assert "RUN_COLLECTSTATIC=False" in text


def test_env_prod_uses_non_default_secret_placeholders() -> None:
    text = _project_template_file(".env.prod-tpl")

    assert "DJANGO_SECRET_KEY=REPLACE_WITH_LONG_RANDOM_SECRET_KEY" in text
    assert "DJANGO_SUPERUSER_PASSWORD=REPLACE_WITH_STRONG_PASSWORD" in text
    assert "change_me_in_production_with_a_long_random_string" not in text
    assert "DJANGO_SUPERUSER_PASSWORD=change_me" not in text


def test_env_prod_sets_asgi_runtime_defaults() -> None:
    text = _project_template_file(".env.prod-tpl")

    assert "DJANGO_SERVER_MODE=asgi" in text
    assert "DJANGO_ASGI_MODULE=root.asgi:application" in text
    assert "ASGI_BIND=0.0.0.0" in text
    assert "ASGI_PORT=8000" in text


def test_env_prod_exposes_backup_retention_override() -> None:
    text = _project_template_file(".env.prod-tpl")

    assert "BACKUP_RETENTION_DAYS=30" in text


def test_entrypoint_defaults_to_asgi_server_with_wsgi_fallback() -> None:
    text = _project_template_file("deploy", "docker", "entrypoint.sh")

    assert 'SERVER_MODE=${DJANGO_SERVER_MODE:-asgi}' in text
    assert 'if [ "$SERVER_MODE" = "wsgi" ]; then' in text
    assert "exec daphne \\" in text


def test_backup_script_does_not_use_pipeline_success_for_pg_dump() -> None:
    text = _project_template_file("deploy", "backup.sh")

    assert '--dbname="$DATABASE_URL"' in text
    assert '--file="$BACKUP_FILE"' in text
    assert "--format=custom" in text
    assert "| gzip >" not in text


def test_backup_script_checks_pg_dump_major_against_server_major() -> None:
    text = _project_template_file("deploy", "backup.sh")

    assert "SHOW server_version_num;" in text
    assert "pg_dump major version (" in text
    assert "DATABASE_URL is required in .env.prod." in text


def test_compose_healthcheck_uses_http_readiness_probe() -> None:
    text = _project_template_file("deploy", "docker", "docker-compose.yml")

    assert "/health/ready/" in text
    assert "socket.socket()" not in text


def test_compose_does_not_include_backup_service() -> None:
    text = _project_template_file("deploy", "docker", "docker-compose.yml")

    assert "\n  backup:\n" not in text


def test_compose_exposes_nginx_on_port_8000_only() -> None:
    text = _project_template_file("deploy", "docker", "docker-compose.yml")

    assert '- "8000:8000"' in text
    assert '- "80:80"' not in text
    assert '- "443:443"' not in text


def test_compose_mounts_cache_directory_for_shared_runtime_cache() -> None:
    text = _project_template_file("deploy", "docker", "docker-compose.yml")

    assert "${CACHE_PATH:-../../cache}:/home/app/web/cache" in text


def test_compose_builds_nginx_image_from_scaffold_template() -> None:
    text = _project_template_file("deploy", "docker", "docker-compose.yml")

    assert "dockerfile: deploy/nginx/Dockerfile" in text
    assert "../nginx/default.conf:/etc/nginx/conf.d/default.conf:ro" not in text
    assert "../nginx/certs:/etc/nginx/certs:ro" not in text


def test_compose_uses_env_prod_file() -> None:
    text = _project_template_file("deploy", "docker", "docker-compose.yml")

    assert "../../.env.prod" in text


def test_env_dev_uses_development_settings_module() -> None:
    text = _project_template_file(".env.dev-tpl")

    assert "DJANGO_DEBUG=True" in text
    assert "DJANGO_SETTINGS_MODULE=root.settings.development" in text


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


def test_deploy_script_waits_for_https_readiness_probe_via_nginx() -> None:
    text = _project_template_file("deploy", "deploy.sh")

    assert "RAIL_READINESS_HOST" in text
    assert '"https://nginx:8000/health/ready/"' in text
    assert 'headers={"Host": host}' in text
    assert 'candidates = [host] if host == "localhost" else [host, "localhost"]' not in text
    assert "ssl._create_unverified_context()" in text
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


def test_deploy_script_bootstraps_secret_and_rejects_weak_superuser_password() -> None:
    text = _project_template_file("deploy", "deploy.sh")

    assert 'if is_insecure_secret "$secret_key"; then' in text
    assert "generating a secure value in .env.prod" in text
    assert 'set_env_value "DJANGO_SECRET_KEY" "$secret_key"' in text
    assert 'if is_insecure_secret "$su_password"; then' in text
    assert "DJANGO_SUPERUSER_PASSWORD appears to use a placeholder" in text


def test_project_template_gitignore_covers_runtime_artifacts() -> None:
    text = _project_template_file(".gitignore")

    assert ".env.dev" in text
    assert ".env.prod" in text
    assert "media/" in text
    assert "backups/" in text
    assert "cache/" in text


def test_base_settings_selects_env_file_by_settings_module() -> None:
    text = _project_template_file("root", "settings", "base.py-tpl")

    assert "_env_filename = \".env.prod\"" in text
    assert "_env_filename = \".env.dev\"" in text
    assert "Missing required environment file" in text


def test_base_settings_allow_csrf_trusted_origins_override() -> None:
    text = _project_template_file("root", "settings", "base.py-tpl")

    assert 'CSRF_TRUSTED_ORIGINS = env.list(' in text
    assert '"CSRF_TRUSTED_ORIGINS"' in text
    assert "default=CORS_ALLOWED_ORIGINS" in text


def test_project_template_dockerignore_keeps_nginx_tls_assets_for_build() -> None:
    text = _project_template_file(".dockerignore")

    assert "deploy/nginx/certs/*.crt" not in text
    assert "deploy/nginx/certs/*.key" not in text


def test_nginx_template_restricts_sensitive_health_diagnostics() -> None:
    text = _project_template_file("deploy", "nginx", "default.conf")

    assert "listen 8000 ssl;" in text
    assert "listen 443 ssl;" not in text
    assert "listen 80;" not in text
    assert "location ~ ^/health/(api|metrics|components|history)/?$ {" in text
    assert "location ~ ^/api/v1/health/?$ {" in text
    assert "allow 127.0.0.1;" in text
    assert "deny all;" in text


def test_nginx_dockerfile_embeds_config_and_tls_assets() -> None:
    text = _project_template_file("deploy", "nginx", "Dockerfile")

    assert "FROM nginx:1.25-alpine" in text
    assert "COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf" in text
    assert "COPY deploy/nginx/certs/ /etc/nginx/certs/" in text


def test_deploy_usage_manual_steps_run_schema_tasks_before_starting_services() -> None:
    text = _project_template_file("deploy", "USAGE.md")

    build_cmd = "docker-compose -f deploy/docker/docker-compose.yml build web nginx"
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


def test_production_template_requires_superuser_for_graphiql_when_enabled() -> None:
    text = _project_template_file("root", "settings", "production.py-tpl")

    assert "'RAIL_PROD_GRAPHIQL_ALLOWED_HOSTS'" in text
    assert "default=ALLOWED_HOSTS" in text
    assert '"authentication_required": True' in text
    assert '"graphiql_superuser_only": True' in text
    assert '"graphiql_allowed_hosts": PROD_GRAPHIQL_ALLOWED_HOSTS' in text


def test_production_template_adds_graphql_security_middleware_after_auth() -> None:
    text = _project_template_file("root", "settings", "production.py-tpl")

    assert "rail_django.middleware.auth.GraphQLAuthenticationMiddleware" in text
    assert "rail_django.middleware.auth.GraphQLRateLimitMiddleware" in text
    assert '_auth_middleware = "django.contrib.auth.middleware.AuthenticationMiddleware"' in text
    assert "MIDDLEWARE.insert(_insert_at, mw)" in text


def test_root_urls_use_superuser_protected_welcome_view() -> None:
    text = _project_template_file("root", "urls.py-tpl")

    assert "from rail_django.http.views.welcome import WelcomeView" in text
    assert "path('', WelcomeView.as_view(), name='welcome')" in text
    assert "TemplateView.as_view" not in text


def test_root_welcome_view_requires_authenticated_superuser() -> None:
    text = _rail_django_file("http", "views", "welcome.py")

    assert "class SuperuserRequiredTemplateView(TemplateView):" in text
    assert "if not user.is_authenticated:" in text
    assert "redirect_to_login(" in text
    assert "if not user.is_superuser:" in text
    assert 'raise PermissionDenied("Superuser access required.")' in text
    assert "class WelcomeView(SuperuserRequiredTemplateView):" in text
    assert "class EndpointGuideView(SuperuserRequiredTemplateView):" in text
    assert '"rail-endpoint-guide"' in text
    assert 'context["api_sections"]' in text
    assert 'context["system_dashboards"]' in text
    assert "/api/v1/templates/catalog/" in text
    assert "/audit/dashboard/" in text
    assert "/health/" in text
    assert "/control-center/" in text


def test_welcome_template_uses_package_source() -> None:
    project_welcome = _project_template_path("root", "templates", "root", "welcome.html")
    package_source = _rail_django_file("templates", "root", "welcome.html")

    assert not project_welcome.is_file()
    assert "{{ request.user.username }}" in package_source
    assert "{% for panel in system_dashboards %}" in package_source
    assert "{% for section in api_sections %}" in package_source
    assert "{% for item in section.items %}" in package_source


def test_rail_urls_include_endpoint_guide_route() -> None:
    text = _rail_django_file("urls.py")

    assert '"ops/endpoints/<slug:endpoint_key>/"' in text
    assert 'name="rail-endpoint-guide"' in text


def test_rail_urls_include_control_center_routes() -> None:
    text = _rail_django_file("urls.py")

    assert "from .http.urls.control_center import control_center_urlpatterns" in text
    assert "urlpatterns += control_center_urlpatterns" in text


def test_endpoint_guide_template_is_scaffolded() -> None:
    text = _project_template_file("root", "templates", "root", "endpoint_guide.html")

    assert "{{ welcome_url }}" in text
    assert "{{ endpoint.path }}" in text
    assert "{{ endpoint.sample_curl }}" in text
