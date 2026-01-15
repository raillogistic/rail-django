"""
Base settings for projects using rail-django framework.
Users import * from this file in their project's settings.py.
"""

import copy
import json
import os
from pathlib import Path

from django.db.backends.signals import connection_created

from rail_django.defaults import LIBRARY_DEFAULTS

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# This BASE_DIR is a placeholder; the project's settings.py will redefine it
# relative to itself, but we provide a fallback here.
BASE_DIR = Path(os.getcwd())

# SECURITY WARNING: keep the secret key used in production secret!
# Default fallback key - projects MUST override this or set env var.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "django-insecure-framework-default-key-change-me"
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party apps
    "graphene_django",
    "django_filters",
    "corsheaders",
    # Framework apps
    "rail_django",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "rail_django.middleware.performance.GraphQLPerformanceMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


def _sqlite_json_valid(value):
    if value is None:
        return 0
    try:
        json.loads(value)
        return 1
    except (TypeError, ValueError):
        return 0


def _sqlite_json(value):
    if value is None:
        return None
    try:
        json.loads(value)
        return value
    except (TypeError, ValueError):
        return None


def _register_sqlite_functions(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    connection.connection.create_function("JSON", 1, _sqlite_json)
    connection.connection.create_function("JSON_VALID", 1, _sqlite_json_valid)


connection_created.connect(_register_sqlite_functions)

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# GraphQL settings
GRAPHENE = {
    "MIDDLEWARE": [],
}
if DEBUG:
    GRAPHENE["MIDDLEWARE"].append("graphene_django.debug.DjangoDebugMiddleware")

# CORS settings
CORS_ALLOW_ALL_ORIGINS = (
    os.environ.get("CORS_ALLOW_ALL_ORIGINS", "False").lower() == "true"
)
CORS_ALLOWED_ORIGINS = (
    os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if os.environ.get("CORS_ALLOWED_ORIGINS")
    else []
)

# Load library defaults into Django settings
RAIL_DJANGO_GRAPHQL = copy.deepcopy(LIBRARY_DEFAULTS)
if DEBUG:
    RAIL_DJANGO_GRAPHQL.setdefault("security_settings", {})[
        "enable_query_depth_limiting"
    ] = False
APPEND_SLASH = True

# Audit logging defaults
AUDIT_STORE_IN_DATABASE = True
