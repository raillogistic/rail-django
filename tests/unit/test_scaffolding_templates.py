"""Unit tests for project scaffolding templates."""

from importlib import resources

import pytest

pytestmark = pytest.mark.unit


def _project_template_file(*relative_parts: str) -> str:
    return (
        resources.files("rail_django")
        .joinpath("scaffolding", "project_template", *relative_parts)
        .read_text(encoding="utf-8")
    )


def _project_template_path(*relative_parts: str):
    return resources.files("rail_django").joinpath(
        "scaffolding", "project_template", *relative_parts
    )


def _rail_django_file(*relative_parts: str) -> str:
    return (
        resources.files("rail_django")
        .joinpath(*relative_parts)
        .read_text(encoding="utf-8")
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


def test_production_template_disables_persistent_database_connections_for_asgi() -> (
    None
):
    settings_text = _project_template_file("root", "settings", "production.py-tpl")
    env_text = _project_template_file(".env.prod-tpl")

    assert "CONN_MAX_AGE', default=0" in settings_text
    assert "CONN_MAX_AGE=0" in env_text


def test_entrypoint_defaults_to_asgi_server_with_wsgi_fallback() -> None:
    text = _project_template_file("entrypoint.sh")

    assert '${DJANGO_SERVER_MODE:-asgi}" = "wsgi"' in text
    assert "root.wsgi:application" in text
    assert "root.asgi:application" in text
    assert "uvicorn_worker.UvicornWorker" in text
    assert "${RUN_MIGRATIONS:-false}" in text
    assert "${RUN_COLLECTSTATIC:-false}" in text


def test_env_dev_uses_development_settings_module() -> None:
    text = _project_template_file(".env.dev-tpl")

    assert "DJANGO_DEBUG=True" in text
    assert "DJANGO_SETTINGS_MODULE=root.settings.development" in text


def test_project_template_gitignore_covers_runtime_artifacts() -> None:
    text = _project_template_file(".gitignore")

    assert ".env.dev" in text
    assert ".env.prod" in text
    assert "media/" in text
    assert "backups/" in text
    assert "cache/" in text


def test_base_settings_selects_env_file_by_settings_module() -> None:
    text = _project_template_file("root", "settings", "base.py-tpl")

    assert '_env_filename = ".env.prod"' in text
    assert '_env_filename = ".env.dev"' in text
    assert "Missing required environment file" in text


def test_base_settings_allow_csrf_trusted_origins_override() -> None:
    text = _project_template_file("root", "settings", "base.py-tpl")

    assert "CSRF_TRUSTED_ORIGINS = env.list(" in text
    assert '"CSRF_TRUSTED_ORIGINS"' in text
    assert "default=CORS_ALLOWED_ORIGINS" in text


def test_users_settings_template_allows_owner_updates_without_model_permissions() -> (
    None
):
    text = _project_template_file("apps", "users", "models.py")

    assert "class GraphQLMeta(GraphQLMetaBase):" in text
    assert 'skip_steps=["model_permission", "abac_permission"]' in text
    assert 'fields = GraphQLMetaBase.Fields(read_only=["user"])' in text
    assert 'field="theme"' in text
    assert "condition=can_update_own_settings" in text


def test_users_access_control_template_has_own_settings_update_guard() -> None:
    text = _project_template_file("apps", "users", "access_control.py")

    assert "def can_update_own_settings" in text
    assert (
        "deny_message=\"Operation 'update' is not permitted on UserSettings.\"" in text
    )
    assert "condition=can_update_own_settings" in text


def test_runtime_dockerfile_excludes_dev_editors_and_libffi_dev() -> None:
    text = _project_template_file("Dockerfile.prod")

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
    assert (
        '_auth_middleware = "django.contrib.auth.middleware.AuthenticationMiddleware"'
        in text
    )
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
    project_welcome = _project_template_path(
        "root", "templates", "root", "welcome.html"
    )
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


def test_users_mutation_retries_locked_sqlite_writes_for_table_config_upsert() -> None:
    text = _project_template_file("apps", "users", "mutations.py")

    assert "def _upsert_table_config_with_retry" in text
    assert "database is locked" in text
    assert "Database is busy, please retry in a moment." in text


def test_users_password_reset_stores_only_hashed_bounded_codes() -> None:
    mutations = _project_template_file("apps", "users", "mutations.py")
    model = _project_template_file("apps", "users", "models.py")
    admin = _project_template_file("apps", "users", "admin.py")

    assert "secrets.randbelow" in mutations
    assert "make_password(code)" in mutations
    assert "check_password(code, otp.code)" in mutations
    assert "select_for_update()" in mutations
    assert "PASSWORD_RESET_MAX_ATTEMPTS" in mutations
    assert "failed_attempts = models.PositiveSmallIntegerField" in model
    assert '"code"' not in admin.split("class PasswordResetOTPAdmin", 1)[1]


def test_production_default_cache_is_shared_between_workers() -> None:
    text = _project_template_file("root", "settings", "production.py-tpl")
    default_cache = text.split("'default':", 1)[1].split("'shared':", 1)[0]

    assert "FileBasedCache" in default_cache
    assert "LocMemCache" not in default_cache
