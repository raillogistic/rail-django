"""
PDF templating helpers built on top of WeasyPrint with pluggable renderers.

This module lets models expose printable PDFs by decorating a model method with
`@model_pdf_template`. The decorator registers a dynamic Django view that:
- Finds the related model instance (by PK passed in the URL)
- Renders header/content/footer templates with the instance context and the
  return value of the decorated method
- Applies optional style configuration (margins, fonts, spacing, etc.)
- Streams the generated PDF with the configured renderer
- Supports async jobs, catalog/preview endpoints, and optional post-processing

Usage inside a model:
    from rail_django.extensions.templating import model_pdf_template

    class WorkOrder(models.Model):
        ...

        @model_pdf_template(
            content=\"pdf/workorders/detail.html\",
            header=\"pdf/shared/header.html\",
            footer=\"pdf/shared/footer.html\",
            url=\"workorders/printable/detail\",
            config={\"margin\": \"15mm\", \"font_family\": \"Inter, sans-serif\"},
        )
        def printable_detail(self):
            return {\"title\": f\"OT #{self.pk}\", \"lines\": self.lines.all()}

The view is automatically available at:
    /api/templates/workorders/printable/detail/<pk>/

If `url` is omitted, the default path is: <app_label>/<model_name>/<function_name>.
Default header/footer templates and style configuration come from
`settings.RAIL_DJANGO_GRAPHQL_TEMPLATING`.
"""

import hashlib
import html
import inspect
import io
import ipaddress
import json
import logging
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Type
from urllib.parse import unquote, urljoin, urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import class_prepared
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.template import loader
from django.urls import path
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

try:
    from weasyprint import HTML
    from weasyprint.urls import default_url_fetcher

    WEASYPRINT_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    HTML = None
    default_url_fetcher = None
    WEASYPRINT_AVAILABLE = False

# Optional pydyf version guard (WeasyPrint 61.x expects >=0.11.0)
try:
    import pydyf  # type: ignore
    from packaging.version import InvalidVersion, Version

    PYDYF_VERSION = getattr(pydyf, "__version__", "0.0.0")
except ImportError:  # pragma: no cover - environment specific
    pydyf = None
    PYDYF_VERSION = None
    Version = None
    InvalidVersion = None

# Optional PDF post-processing (watermark/encryption/signature)
try:
    from pypdf import PdfReader, PdfWriter  # type: ignore

    PYPDF_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    PdfReader = None
    PdfWriter = None
    PYPDF_AVAILABLE = False

# Optional GraphQL metadata and permission helpers
try:
    from rail_django.core.meta import get_model_graphql_meta
except ImportError:  # pragma: no cover - fallback during early startup
    get_model_graphql_meta = None

try:
    from rail_django.extensions.auth import get_user_from_token
except ImportError:  # pragma: no cover - fallback when auth not available
    get_user_from_token = None

try:
    from rail_django.extensions.permissions import (
        OperationType,
        permission_manager,
    )
except ImportError:  # pragma: no cover - optional permission subsystem
    OperationType = None
    permission_manager = None

try:
    from rail_django.security.rbac import role_manager
except ImportError:  # pragma: no cover - security optional
    role_manager = None

# Optional JWT protection (mirrors export endpoints)
try:
    from .auth_decorators import jwt_required
except ImportError:
    jwt_required = None

try:
    from .audit import AuditEventType, log_audit_event
except ImportError:
    AuditEventType = None
    log_audit_event = None

logger = logging.getLogger(__name__)

TEMPLATE_RATE_LIMIT_DEFAULTS = {
    "enable": True,
    "window_seconds": 60,
    "max_requests": 30,
    "trusted_proxies": [],
}

TEMPLATE_CACHE_DEFAULTS = {
    "enable": False,
    "timeout_seconds": 300,
    "vary_on_user": True,
    "vary_on_client_data": True,
    "vary_on_template_config": True,
    "key_prefix": "rail:pdf_cache",
}

TEMPLATE_ASYNC_DEFAULTS = {
    "enable": False,
    "backend": "thread",
    "expires_seconds": 3600,
    "storage_dir": None,
    "queue": "default",
    "track_progress": False,
    "webhook_url": None,
    "webhook_headers": {},
    "webhook_timeout_seconds": 10,
}

TEMPLATE_CATALOG_DEFAULTS = {
    "enable": True,
    "require_authentication": True,
    "filter_by_access": True,
    "include_config": False,
    "include_permissions": True,
}

TEMPLATE_URL_FETCHER_DEFAULTS = {
    "schemes": ["file", "data", "http", "https"],
    "hosts": [],
    "allow_remote": False,
    "file_roots": [],
}

TEMPLATE_POSTPROCESS_DEFAULTS = {
    "enable": False,
    "strict": True,
    "encryption": {},
    "signature": {},
    "watermark": {},
    "page_stamps": {},
}


def _merge_dict(defaults: dict[str, Any], overrides: Any) -> dict[str, Any]:
    """Shallow-merge dict settings with safe fallbacks."""
    merged = dict(defaults)
    if isinstance(overrides, dict):
        merged.update(overrides)
    return merged


def _patch_pydyf_pdf() -> None:
    """
    Patch legacy pydyf.PDF signature to accept version/identifier.

    Some environments ship pydyf with an outdated constructor
    (`__init__(self)`) even though the package version reports >=0.11.0.
    WeasyPrint>=61 passes (version, identifier) to the constructor and
    expects a `version` attribute on the instance, causing a TypeError.
    This shim makes the constructor compatible without altering runtime
    behaviour for already-compatible versions.
    """
    if not pydyf or not hasattr(pydyf, "PDF"):
        return

    pdf_cls = pydyf.PDF
    if getattr(pdf_cls, "_rail_patched_pdf_ctor", False):
        return

    try:
        params = inspect.signature(pdf_cls.__init__).parameters
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return

    # Legacy signature only includes `self`
    if len(params) == 1:
        original_init = pdf_cls.__init__

        def patched_init(self, version: Any = b"1.7", identifier: Any = None) -> None:
            original_init(self)  # type: ignore[misc]
            # Persist requested version/identifier so pdf.write(...) receives them.
            requested_version = version or b"1.7"
            if isinstance(requested_version, str):
                requested_version = requested_version.encode("ascii", "ignore")
            elif not isinstance(requested_version, (bytes, bytearray)):
                requested_version = str(requested_version).encode("ascii", "ignore")
            else:
                requested_version = bytes(requested_version)

            self.version = requested_version
            self.identifier = identifier

        pdf_cls.__init__ = patched_init  # type: ignore[assignment]
        setattr(pdf_cls, "_rail_patched_pdf_ctor", True)
        logger.warning(
            "Patched legacy pydyf.PDF constructor for compatibility with WeasyPrint; "
            "consider upgrading pydyf to a build exposing the modern signature."
        )


def _templating_settings() -> dict[str, Any]:
    """
    Safely read the templating defaults from settings.

    Returns:
        A dictionary with header/footer defaults and style defaults.
    """
    return getattr(settings, "RAIL_DJANGO_GRAPHQL_TEMPLATING", {})


def _templating_dict(key: str, defaults: dict[str, Any]) -> dict[str, Any]:
    return _merge_dict(defaults, _templating_settings().get(key))


def _templating_rate_limit() -> dict[str, Any]:
    return _templating_dict("rate_limit", TEMPLATE_RATE_LIMIT_DEFAULTS)


def _templating_cache() -> dict[str, Any]:
    return _templating_dict("cache", TEMPLATE_CACHE_DEFAULTS)


def _templating_async() -> dict[str, Any]:
    return _templating_dict("async_jobs", TEMPLATE_ASYNC_DEFAULTS)


def _templating_catalog() -> dict[str, Any]:
    return _templating_dict("catalog", TEMPLATE_CATALOG_DEFAULTS)


def _templating_url_fetcher_allowlist() -> dict[str, Any]:
    return _templating_dict("url_fetcher_allowlist", TEMPLATE_URL_FETCHER_DEFAULTS)


def _templating_postprocess_defaults() -> dict[str, Any]:
    return _templating_dict("postprocess", TEMPLATE_POSTPROCESS_DEFAULTS)


def _templating_renderer_name() -> str:
    return str(_templating_settings().get("renderer", "weasyprint"))


def _templating_expose_errors() -> bool:
    return bool(_templating_settings().get("expose_errors", settings.DEBUG))


def _templating_preview_enabled() -> bool:
    return bool(_templating_settings().get("enable_preview", settings.DEBUG))


def _default_template_config() -> dict[str, str]:
    """
    Provide default styling that can be overridden per template.

    Returns:
        Dict of CSS-friendly configuration values.
    """
    defaults = {
        "page_size": "A4",
        "orientation": "portrait",
        "margin": "10mm",
        "padding": "0",
        "font_family": "Arial, sans-serif",
        "font_size": "12pt",
        "text_color": "#222222",
        "background_color": "#ffffff",
        "header_spacing": "10mm",
        "footer_spacing": "12mm",
        "content_spacing": "8mm",
        "extra_css": "",
    }
    settings_overrides = _templating_settings().get("default_template_config", {})
    return {**defaults, **settings_overrides}


def _default_header() -> str:
    """Return the default header template path."""
    return _templating_settings().get(
        "default_header_template", "pdf/default_header.html"
    )


def _default_footer() -> str:
    """Return the default footer template path."""
    return _templating_settings().get(
        "default_footer_template", "pdf/default_footer.html"
    )


def _url_prefix() -> str:
    """Return URL prefix under /api/ where templates are exposed."""
    return _templating_settings().get("url_prefix", "templates")


def _default_file_roots() -> list[Path]:
    roots: list[Path] = []
    candidates = [
        getattr(settings, "STATIC_ROOT", None),
        getattr(settings, "MEDIA_ROOT", None),
    ]
    base_dir = getattr(settings, "BASE_DIR", None)
    if base_dir:
        base_path = Path(base_dir)
        candidates.extend(
            [
                base_path / "static",
                base_path / "staticfiles",
                base_path / "media",
                base_path / "mediafiles",
            ]
        )
    for candidate in candidates:
        if not candidate:
            continue
        try:
            path = Path(candidate)
        except TypeError:
            continue
        roots.append(path)
    return roots


def _resolve_file_roots(allowlist: dict[str, Any]) -> list[Path]:
    file_roots = allowlist.get("file_roots") or []
    roots: list[Path] = []
    if file_roots:
        for entry in file_roots:
            try:
                roots.append(Path(entry))
            except TypeError:
                continue
    if not roots:
        roots = _default_file_roots()
    return roots


def _path_within_roots(path: Path, roots: Iterable[Path]) -> bool:
    try:
        resolved = path.resolve()
    except Exception:
        return False
    for root in roots:
        try:
            root_resolved = root.resolve()
        except Exception:
            continue
        try:
            resolved.relative_to(root_resolved)
            return True
        except ValueError:
            continue
    return False


def _file_path_from_url(url: str) -> Optional[Path]:
    parsed = urlparse(url)
    if parsed.scheme and len(parsed.scheme) == 1 and parsed.path.startswith("\\"):
        path = f"{parsed.scheme}:{parsed.path}"
    elif parsed.scheme in ("", "file"):
        path = parsed.path or url
    else:
        return None
    path = unquote(path)
    if path.startswith("/") and len(path) > 2 and path[2] == ":":
        path = path.lstrip("/")
    return Path(path)


def _build_safe_url_fetcher(base_url: Optional[str]) -> Optional[Callable]:
    if not default_url_fetcher:
        return None

    allowlist = _templating_url_fetcher_allowlist()
    allowed_schemes = {str(item).lower() for item in allowlist.get("schemes") or []}
    allow_remote = bool(allowlist.get("allow_remote", False))
    allowed_hosts = {
        str(item).lower() for item in allowlist.get("hosts") or [] if str(item)
    }
    file_roots = _resolve_file_roots(allowlist)
    base_path = _file_path_from_url(str(base_url)) if base_url else None
    base_parsed = urlparse(str(base_url)) if base_url else None
    base_scheme = (base_parsed.scheme or "").lower() if base_parsed else ""
    base_host = (base_parsed.hostname or "").lower() if base_parsed else ""
    base_is_http = base_scheme in ("http", "https")

    def safe_fetcher(url: str) -> dict[str, Any]:
        resolved_url = url
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()
        file_path = None

        if not scheme and base_is_http and base_url:
            resolved_url = urljoin(str(base_url), url)
            parsed = urlparse(resolved_url)
            scheme = (parsed.scheme or "").lower()

        if scheme in ("", "file"):
            file_path = _file_path_from_url(resolved_url)
            if file_path and not file_path.is_absolute() and base_path:
                file_path = (base_path / file_path).resolve()
                resolved_url = str(file_path)

        scheme_check = scheme or ("file" if file_path else "")
        if scheme_check and scheme_check not in allowed_schemes:
            raise ValueError(f"Blocked URL scheme: {scheme_check}")

        if scheme in ("http", "https") or (not scheme and base_is_http):
            host = (parsed.hostname or base_host or "").lower()
            if not allow_remote and host not in allowed_hosts:
                raise ValueError("Remote URL fetch blocked by allowlist")
        elif file_path:
            if file_roots and not _path_within_roots(file_path, file_roots):
                raise ValueError("File URL fetch blocked by allowlist")

        return default_url_fetcher(resolved_url)

    return safe_fetcher


@dataclass
class TemplateMeta:
    """Raw decorator metadata attached to a model method."""

    header_template: Optional[str]
    content_template: str
    footer_template: Optional[str]
    url_path: Optional[str]
    config: dict[str, Any] = field(default_factory=dict)
    roles: Sequence[str] = field(default_factory=tuple)
    permissions: Sequence[str] = field(default_factory=tuple)
    guard: Optional[str] = None
    require_authentication: bool = True
    title: Optional[str] = None
    allow_client_data: bool = False
    client_data_fields: Sequence[str] = field(default_factory=tuple)
    client_data_schema: Sequence[dict[str, Any]] = field(default_factory=tuple)


@dataclass
class TemplateDefinition:
    """Runtime representation of a registered PDF template."""

    model: Optional[type[models.Model]]
    method_name: Optional[str]
    handler: Optional[Callable[..., Any]]
    source: str
    header_template: str
    content_template: str
    footer_template: str
    url_path: str
    config: dict[str, Any]
    roles: Sequence[str]
    permissions: Sequence[str]
    guard: Optional[str]
    require_authentication: bool
    title: str
    allow_client_data: bool
    client_data_fields: Sequence[str]
    client_data_schema: Sequence[dict[str, Any]]


@dataclass
class TemplateAccessDecision:
    """Represents whether a user can access a template."""

    allowed: bool
    reason: Optional[str] = None
    status_code: int = 200


def _derive_template_title(model: models.Model, method_name: str) -> str:
    """
    Compute a readable fallback title when none is provided.

    Args:
        model: Django model class owning the template.
        method_name: Name of the decorated method.

    Returns:
        Human-readable title.
    """

    base = method_name.replace("_", " ").strip() or "Impression"
    base = base[:1].upper() + base[1:]
    verbose_name = getattr(getattr(model, "_meta", None), "verbose_name", None)
    if verbose_name:
        return f"{base} ({verbose_name})"
    return base


def _derive_function_title(func: Callable) -> str:
    """Compute a readable fallback title for function templates."""
    base = getattr(func, "__name__", "").replace("_", " ").strip() or "PDF"
    return base[:1].upper() + base[1:]


def _clean_client_value(value: Any) -> str:
    """Normalize client-provided values to bounded strings."""

    try:
        if value is None:
            return ""
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8", "ignore")
        text = str(value)
    except Exception:
        text = ""

    return text[:1024]


def _normalize_client_schema(
    fields: Sequence[str], schema: Sequence[dict[str, Any]]
) -> Sequence[dict[str, Any]]:
    """
    Normalize client data schema. When explicit schema is provided, enforce name/type.
    Otherwise derive from field names.
    """

    normalized: dict[str, dict[str, Any]] = {}

    for entry in schema or []:
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        field_type = str(entry.get("type", "string")).strip().lower() or "string"
        normalized[name] = {"name": name, "type": field_type}

    for name in fields or []:
        if name in normalized:
            continue
        normalized[str(name)] = {"name": str(name), "type": "string"}

    return tuple(normalized.values())


class TemplateRegistry:
    """Keeps track of all registered PDF templates exposed by models."""

    def __init__(self) -> None:
        self._templates: dict[str, TemplateDefinition] = {}

    def register(
        self, model: type[models.Model], method_name: str, meta: TemplateMeta
    ) -> None:
        """
        Register a template for a model method.

        Args:
            model: Django model class owning the method.
            method_name: Name of the decorated method.
            meta: Raw decorator metadata.
        """
        if not meta.content_template:
            raise ValueError(
                f"content_template is required for PDF templating on {model.__name__}.{method_name}"
            )

        app_label = model._meta.app_label
        model_name = model._meta.model_name
        url_path = meta.url_path or f"{app_label}/{model_name}/{method_name}"

        merged_config = {**_default_template_config(), **(meta.config or {})}
        header = meta.header_template or _default_header()
        footer = meta.footer_template or _default_footer()
        title = meta.title or _derive_template_title(model, method_name)
        schema = _normalize_client_schema(
            meta.client_data_fields, meta.client_data_schema
        )

        definition = TemplateDefinition(
            model=model,
            method_name=method_name,
            handler=None,
            source="model",
            header_template=header,
            content_template=meta.content_template,
            footer_template=footer,
            url_path=url_path,
            config=merged_config,
            roles=tuple(meta.roles or ()),
            permissions=tuple(meta.permissions or ()),
            guard=meta.guard,
            require_authentication=meta.require_authentication,
            title=title,
            allow_client_data=bool(meta.allow_client_data),
            client_data_fields=tuple(meta.client_data_fields or ()),
            client_data_schema=schema,
        )

        self._templates[url_path] = definition
        logger.info(
            "Registered PDF template for %s.%s at /api/%s/%s/<pk>/",
            model.__name__,
            method_name,
            _url_prefix(),
            url_path,
        )

    def register_function(self, func: Callable, meta: TemplateMeta) -> None:
        """
        Register a PDF template for a standalone function.

        Args:
            func: Callable that returns context data for the template.
            meta: Raw decorator metadata.
        """
        if not meta.content_template:
            raise ValueError("content_template is required for PDF templating")

        module_label = str(getattr(func, "__module__", "")).split(".")[-1] or "pdf"
        url_path = meta.url_path or f"{module_label}/{func.__name__}"

        merged_config = {**_default_template_config(), **(meta.config or {})}
        header = meta.header_template or _default_header()
        footer = meta.footer_template or _default_footer()
        title = meta.title or _derive_function_title(func)
        schema = _normalize_client_schema(
            meta.client_data_fields, meta.client_data_schema
        )

        definition = TemplateDefinition(
            model=None,
            method_name=None,
            handler=func,
            source="function",
            header_template=header,
            content_template=meta.content_template,
            footer_template=footer,
            url_path=url_path,
            config=merged_config,
            roles=tuple(meta.roles or ()),
            permissions=tuple(meta.permissions or ()),
            guard=meta.guard,
            require_authentication=meta.require_authentication,
            title=title,
            allow_client_data=bool(meta.allow_client_data),
            client_data_fields=tuple(meta.client_data_fields or ()),
            client_data_schema=schema,
        )

        self._templates[url_path] = definition
        logger.info(
            "Registered function PDF template for %s at /api/%s/%s/<pk>/",
            func.__name__,
            _url_prefix(),
            url_path,
        )

    def get(self, url_path: str) -> Optional[TemplateDefinition]:
        """Retrieve a registered template by its URL path."""
        return self._templates.get(url_path)

    def all(self) -> dict[str, TemplateDefinition]:
        """Expose all templates (primarily for introspection and tests)."""
        return dict(self._templates)


template_registry = TemplateRegistry()


def model_pdf_template(
    *,
    content: str,
    header: Optional[str] = None,
    footer: Optional[str] = None,
    url: Optional[str] = None,
    config: Optional[dict[str, Any]] = None,
    roles: Optional[Iterable[str]] = None,
    permissions: Optional[Iterable[str]] = None,
    guard: Optional[str] = None,
    require_authentication: bool = True,
    title: Optional[str] = None,
    allow_client_data: bool = False,
    client_data_fields: Optional[Iterable[str]] = None,
    client_data_schema: Optional[Iterable[dict[str, Any]]] = None,
) -> Callable:
    """
    Decorator to expose a model method as a PDF endpoint rendered with WeasyPrint.

    Args:
        content: Path to the main content template (required).
        header: Path to the header template. Uses default from settings when omitted.
        footer: Path to the footer template. Uses default from settings when omitted.
        url: Relative URL (under /api/<prefix>/) for the PDF endpoint. Defaults to
             <app_label>/<model_name>/<function_name>.
        config: Optional style overrides (margin, padding, fonts, page_size, etc.).
        roles: Optional iterable of RBAC role names required to access the PDF.
        permissions: Optional iterable of Django permission strings required.
        guard: Optional GraphQL guard name (defaults to "retrieve" when omitted).
        require_authentication: Whether authentication is mandatory (default True).
        title: Optional human-readable label surfaced to the frontend.
        allow_client_data: When True, whitelisted query parameters can be injected into the template context.
        client_data_fields: Iterable of allowed client data keys (whitelist). Ignored when allow_client_data is False.
        client_data_schema: Optional iterable of dicts {"name": str, "type": str} to describe expected client fields.

    Returns:
        The original function with attached metadata for automatic registration.
    """

    def decorator(func: Callable) -> Callable:
        func._pdf_template_meta = TemplateMeta(
            header_template=header,
            content_template=content,
            footer_template=footer,
            url_path=url,
            config=config or {},
            roles=tuple(roles or ()),
            permissions=tuple(permissions or ()),
            guard=guard,
            require_authentication=require_authentication,
            title=title,
            allow_client_data=allow_client_data,
            client_data_fields=tuple(client_data_fields or ()),
            client_data_schema=tuple(client_data_schema or ()),
        )
        return func

    return decorator


def pdf_template(
    *,
    content: str,
    header: Optional[str] = None,
    footer: Optional[str] = None,
    url: Optional[str] = None,
    config: Optional[dict[str, Any]] = None,
    roles: Optional[Iterable[str]] = None,
    permissions: Optional[Iterable[str]] = None,
    guard: Optional[str] = None,
    require_authentication: bool = True,
    title: Optional[str] = None,
    allow_client_data: bool = False,
    client_data_fields: Optional[Iterable[str]] = None,
    client_data_schema: Optional[Iterable[dict[str, Any]]] = None,
) -> Callable:
    """
    Decorator to expose a standalone function as a PDF endpoint.

    Args:
        content: Path to the main content template (required).
        header: Path to the header template. Uses default from settings when omitted.
        footer: Path to the footer template. Uses default from settings when omitted.
        url: Relative URL (under /api/<prefix>/) for the PDF endpoint. Defaults to
             <module>/<function_name>.
        config: Optional style overrides (margin, padding, fonts, page_size, etc.).
        roles: Optional iterable of RBAC role names required to access the PDF.
        permissions: Optional iterable of Django permission strings required.
        guard: Optional GraphQL guard name (ignored when no model is associated).
        require_authentication: Whether authentication is mandatory (default True).
        title: Optional human-readable label surfaced to the frontend.
        allow_client_data: When True, whitelisted query parameters can be injected into the template context.
        client_data_fields: Iterable of allowed client data keys (whitelist). Ignored when allow_client_data is False.
        client_data_schema: Optional iterable of dicts {"name": str, "type": str} to describe expected client fields.
    """

    def decorator(func: Callable) -> Callable:
        meta = TemplateMeta(
            header_template=header,
            content_template=content,
            footer_template=footer,
            url_path=url,
            config=config or {},
            roles=tuple(roles or ()),
            permissions=tuple(permissions or ()),
            guard=guard,
            require_authentication=require_authentication,
            title=title,
            allow_client_data=allow_client_data,
            client_data_fields=tuple(client_data_fields or ()),
            client_data_schema=tuple(client_data_schema or ()),
        )
        func._pdf_template_meta = meta
        template_registry.register_function(func, meta)
        return func

    return decorator


def _render_template(template_path: Optional[str], context: dict[str, Any]) -> str:
    """
    Render a template path with context. Returns an empty string when no template is provided.

    Args:
        template_path: Path relative to Django templates directories or absolute path.
        context: Context to render.

    Returns:
        Rendered HTML string.
    """
    if not template_path:
        return ""
    template = loader.get_template(template_path)
    return template.render(context)


def _build_style_block(
    config: dict[str, Any], *, extra_css_chunks: Optional[Iterable[str]] = None
) -> str:
    """
    Convert style configuration into a CSS block usable by WeasyPrint.

    Args:
        config: Style configuration merging defaults and overrides.
        extra_css_chunks: Optional list of extra CSS fragments to append.

    Returns:
        CSS string.
    """
    page_size = config.get("page_size", "A4")
    orientation = config.get("orientation", "portrait")
    margin = config.get("margin", "20mm")
    padding = config.get("padding", "12mm")
    font_family = config.get("font_family", "Arial, sans-serif")
    font_size = config.get("font_size", "12pt")
    text_color = config.get("text_color", "#222222")
    background_color = config.get("background_color", "#ffffff")
    header_spacing = config.get("header_spacing", "10mm")
    footer_spacing = config.get("footer_spacing", "12mm")
    content_spacing = config.get("content_spacing", "8mm")
    extra_css = config.get("extra_css", "")

    css_chunks = [
        f"@page {{ size: {page_size} {orientation}; margin: {margin}; }}",
        "body {"
        f" padding: {padding};"
        f" font-family: {font_family};"
        f" font-size: {font_size};"
        f" color: {text_color};"
        f" background: {background_color};"
        " }",
        f".pdf-header {{ margin-bottom: {header_spacing}; }}",
        f".pdf-content {{ margin-bottom: {content_spacing}; }}",
        f".pdf-footer {{ margin-top: {footer_spacing}; }}",
    ]

    if extra_css:
        css_chunks.append(str(extra_css))
    if extra_css_chunks:
        for chunk in extra_css_chunks:
            if chunk:
                css_chunks.append(str(chunk))

    return "\n".join(css_chunks)


def _css_escape(value: str) -> str:
    """
    Escape a string for safe inclusion in CSS content property.

    Escapes backslashes, quotes, newlines, and other control characters
    that could break out of CSS string context.
    """
    result = []
    for char in value:
        if char == "\\":
            result.append("\\\\")
        elif char == '"':
            result.append('\\"')
        elif char == "'":
            result.append("\\'")
        elif char == "\n":
            result.append("\\A ")
        elif char == "\r":
            result.append("\\D ")
        elif char == "\t":
            result.append("\\9 ")
        elif char == "{":
            result.append("\\7B ")
        elif char == "}":
            result.append("\\7D ")
        elif char == "<":
            result.append("\\3C ")
        elif char == ">":
            result.append("\\3E ")
        elif ord(char) < 32 or ord(char) == 127:
            # Escape other control characters
            result.append(f"\\{ord(char):X} ")
        else:
            result.append(char)
    return "".join(result)


def _page_stamp_content(text: str) -> str:
    tokens = re.split(r"(\{page\}|\{pages\})", text)
    parts: list[str] = []
    for token in tokens:
        if token == "{page}":
            parts.append("counter(page)")
        elif token == "{pages}":
            parts.append("counter(pages)")
        elif token:
            parts.append(f"\"{_css_escape(token)}\"")
    return " ".join(parts) if parts else "\"\""


def _build_page_stamp_css(page_stamps: Optional[dict[str, Any]]) -> str:
    if not page_stamps:
        return ""

    position_map = {
        "top-left": "@top-left",
        "top-center": "@top-center",
        "top-right": "@top-right",
        "bottom-left": "@bottom-left",
        "bottom-center": "@bottom-center",
        "bottom-right": "@bottom-right",
    }
    position = position_map.get(
        str(page_stamps.get("position", "bottom-right")).lower(), "@bottom-right"
    )
    text = str(page_stamps.get("text", "Page {page} of {pages}"))
    font_size = str(page_stamps.get("font_size", "9pt"))
    color = str(page_stamps.get("color", "#666666"))
    content = _page_stamp_content(text)

    return (
        "@page { "
        f"{position} {{ content: {content}; font-size: {font_size}; color: {color}; }} "
        "}"
    )


def _build_watermark_assets(watermark: Optional[dict[str, Any]]) -> tuple[str, str]:
    if not watermark:
        return "", ""

    if str(watermark.get("mode", "css")).lower() == "overlay":
        return "", ""

    html_content = watermark.get("html")
    text = watermark.get("text")
    if html_content:
        watermark_html = str(html_content)
    elif text:
        watermark_html = f"<div class='pdf-watermark'>{html.escape(str(text))}</div>"
    else:
        return "", ""

    opacity = watermark.get("opacity", 0.12)
    rotation = watermark.get("rotation", -30)
    font_size = watermark.get("font_size", "48pt")
    color = watermark.get("color", "#999999")
    z_index = watermark.get("z_index", 0)

    watermark_css = (
        ".pdf-watermark {"
        " position: fixed;"
        " top: 50%;"
        " left: 50%;"
        f" transform: translate(-50%, -50%) rotate({rotation}deg);"
        f" opacity: {opacity};"
        f" font-size: {font_size};"
        f" color: {color};"
        f" z-index: {z_index};"
        " pointer-events: none;"
        " white-space: nowrap;"
        "}"
    )

    return watermark_html, watermark_css


def _register_model_templates(sender: Any, **kwargs: Any) -> None:
    """
    Signal handler to register decorated methods once models are ready.

    Args:
        sender: Model class being prepared.
    """
    if not hasattr(sender, "_meta"):
        return
    if sender._meta.abstract:
        return

    for attr_name, attr in inspect.getmembers(sender, predicate=callable):
        meta: Optional[TemplateMeta] = getattr(attr, "_pdf_template_meta", None)
        if not meta:
            continue

        template_registry.register(sender, attr_name, meta)


class_prepared.connect(
    _register_model_templates, dispatch_uid="pdf_template_registration"
)


def _register_existing_models_if_ready() -> None:
    """Register templates for models that were loaded before the module import."""
    try:
        from django.apps import apps

        if not apps.ready:
            return

        for model in apps.get_models():
            _register_model_templates(model)
    except Exception as exc:  # pragma: no cover - defensive during startup
        logger.debug("Skipping eager template registration: %s", exc)


_register_existing_models_if_ready()


def evaluate_template_access(
    template_def: TemplateDefinition,
    user: Optional[Any],
    *,
    instance: Optional[models.Model] = None,
) -> TemplateAccessDecision:
    """
    Determine whether a user can access a registered template.

    Args:
        template_def: Template definition entry.
        user: Django user (may be anonymous/None).
        instance: Optional model instance for guard evaluation.

    Returns:
        TemplateAccessDecision describing the authorization result.
    """

    is_authenticated = bool(user and getattr(user, "is_authenticated", False))

    if template_def.require_authentication and not is_authenticated:
        return TemplateAccessDecision(
            allowed=False,
            reason="Vous devez être authentifié pour accéder à ce document.",
            status_code=401,
        )

    if not is_authenticated:
        # Anonymous access explicitly allowed; no further checks required.
        return TemplateAccessDecision(allowed=True)

    if getattr(user, "is_superuser", False):
        return TemplateAccessDecision(allowed=True)

    required_permissions = tuple(template_def.permissions or ())
    if required_permissions and not any(
        user.has_perm(permission) for permission in required_permissions
    ):
        return TemplateAccessDecision(
            allowed=False,
            reason="Permission manquante pour générer ce document.",
            status_code=403,
        )

    required_roles = tuple(template_def.roles or ())
    if required_roles:
        if not role_manager:
            logger.warning(
                "Role manager unavailable while enforcing template roles for %s",
                template_def.url_path,
            )
            return TemplateAccessDecision(
                allowed=False,
                reason="Le contrôle des rôles est indisponible.",
                status_code=403,
            )
        try:
            user_roles = set(role_manager.get_user_roles(user))
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Unable to fetch roles for %s: %s", user, exc)
            user_roles = set()

        if not user_roles.intersection(set(required_roles)):
            return TemplateAccessDecision(
                allowed=False,
                reason="Rôle requis manquant pour ce document.",
                status_code=403,
            )

    if permission_manager and OperationType and template_def.model:
        try:
            model_label = template_def.model._meta.label_lower
            permission_state = permission_manager.check_operation_permission(
                user, model_label, OperationType.READ
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Permission manager check failed for %s: %s (denying access)",
                template_def.model.__name__,
                exc,
            )
            return TemplateAccessDecision(
                allowed=False,
                reason="Vérification de permission indisponible.",
                status_code=403,
            )
        else:
            if not permission_state.allowed:
                return TemplateAccessDecision(
                    allowed=False,
                    reason=permission_state.reason or "Accès refusé pour ce document.",
                    status_code=403,
                )

    if template_def.model and instance is None:
        return TemplateAccessDecision(allowed=True)

    guard_name = template_def.guard or ("retrieve" if template_def.model else None)
    if guard_name and template_def.model:
        if not get_model_graphql_meta:
            logger.warning(
                "GraphQL meta unavailable while enforcing template guard '%s' for %s",
                guard_name,
                template_def.url_path,
            )
            return TemplateAccessDecision(
                allowed=False,
                reason="Le contrôle d'accès est indisponible.",
                status_code=403,
            )

        graphql_meta = None
        try:
            graphql_meta = get_model_graphql_meta(template_def.model)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(
                "GraphQLMeta unavailable for %s: %s",
                template_def.model.__name__,
                exc,
            )

        if graphql_meta:
            guard_state = None
            try:
                guard_state = graphql_meta.describe_operation_guard(
                    guard_name,
                    user=user,
                    instance=instance,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to evaluate guard '%s' for %s: %s (denying access)",
                    guard_name,
                    template_def.model.__name__,
                    exc,
                )
                return TemplateAccessDecision(
                    allowed=False,
                    reason="Garde d'opération indisponible.",
                    status_code=403,
                )

            if (
                guard_state
                and guard_state.get("guarded")
                and not guard_state.get("allowed", True)
            ):
                return TemplateAccessDecision(
                    allowed=False,
                    reason=guard_state.get("reason")
                    or "Accès refusé par la garde d'opération.",
                    status_code=403,
                )

    return TemplateAccessDecision(allowed=True)


def authorize_template_access(
    request: HttpRequest,
    template_def: TemplateDefinition,
    instance: Optional[models.Model] = None,
) -> Optional[JsonResponse]:
    """
    Authorize access to a PDF template and return a denial response if not allowed.

    Args:
        request: The HTTP request.
        template_def: Template definition to check access for.
        instance: Optional model instance for guard evaluation.

    Returns:
        JsonResponse with error details if access denied, None if allowed.
    """
    user = _resolve_request_user(request)
    decision = evaluate_template_access(
        template_def,
        user=user,
        instance=instance,
    )
    if decision.allowed:
        return None
    detail = decision.reason or (
        "Vous devez être authentifié pour accéder à ce document."
        if decision.status_code == 401
        else "Accès refusé pour ce document."
    )
    return JsonResponse(
        {"error": "Forbidden", "detail": detail}, status=decision.status_code
    )


def _extract_client_data(
    request: HttpRequest, template_def: TemplateDefinition
) -> dict[str, Any]:
    """
    Extract whitelisted client-provided values from the request (query params only).
    """

    if not template_def.allow_client_data:
        return {}

    allowed_keys = {str(k) for k in (template_def.client_data_fields or [])}
    # If schema provided, use its names for additional allowance
    if template_def.client_data_schema:
        for entry in template_def.client_data_schema:
            name = str(entry.get("name", "")).strip()
            if name:
                allowed_keys.add(name)
    if not allowed_keys:
        return {}

    data: dict[str, Any] = {}
    for key in allowed_keys:
        if key in request.GET:
            data[key] = _clean_client_value(request.GET.get(key))

    return data


def _call_model_method(method: Optional[Callable], request: HttpRequest) -> Any:
    if not callable(method):
        return {}
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return method()

    params = signature.parameters
    request_param = params.get("request")
    if not request_param:
        for param in params.values():
            if param.annotation is HttpRequest:
                request_param = param
                break
    if request_param:
        if request_param.kind == request_param.KEYWORD_ONLY:
            return method(request=request)
        return method(request)
    has_var_keyword = any(
        param.kind == param.VAR_KEYWORD for param in params.values()
    )
    has_var_positional = any(
        param.kind == param.VAR_POSITIONAL for param in params.values()
    )
    if has_var_keyword:
        return method(request=request)
    if has_var_positional:
        return method(request)
    return method()


def _call_function_handler(
    handler: Callable, request: HttpRequest, pk: Optional[str]
) -> Any:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return handler(request, pk)

    params = signature.parameters
    positional_params = [
        param
        for param in params.values()
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]
    allows_varargs = any(param.kind == param.VAR_POSITIONAL for param in params.values())
    accepts_kwargs = any(param.kind == param.VAR_KEYWORD for param in params.values())
    request_param = params.get("request")
    args: list[Any] = []
    kwargs: dict[str, Any] = {}

    if request_param:
        if request_param.kind == request_param.KEYWORD_ONLY:
            kwargs["request"] = request
        else:
            args.append(request)
    elif accepts_kwargs:
        kwargs["request"] = request

    if pk is not None:
        if len(args) < len(positional_params) or allows_varargs:
            args.append(pk)
        elif "pk" in params:
            kwargs["pk"] = pk
        elif "id" in params:
            kwargs["id"] = pk
        elif accepts_kwargs:
            kwargs["pk"] = pk

    return handler(*args, **kwargs)


def _build_template_context(
    request: HttpRequest,
    instance: Optional[models.Model],
    template_def: TemplateDefinition,
    client_data: Optional[dict[str, Any]] = None,
    pk: Optional[str] = None,
) -> dict[str, Any]:
    data: Any = {}
    if template_def.source == "model":
        method = getattr(instance, template_def.method_name or "", None)
        data = _call_model_method(method, request)
    elif template_def.handler:
        data = _call_function_handler(template_def.handler, request, pk)

    return {
        "instance": instance,
        "data": data,
        "request": request,
        "template_config": template_def.config,
        "client_data": client_data or {},
    }


def _resolve_request_user(request: HttpRequest):
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return user

    if not get_user_from_token:
        return user

    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header and (
        auth_header.startswith("Bearer ") or auth_header.startswith("Token ")
    ):
        parts = auth_header.split(" ", 1)
        if len(parts) == 2:
            token = parts[1].strip()
            if token:
                try:
                    fallback_user = get_user_from_token(token)
                except Exception:  # pragma: no cover - defensive
                    fallback_user = None
                if fallback_user and getattr(fallback_user, "is_authenticated", False):
                    request.user = fallback_user
                    return fallback_user

    return user


class PdfRenderer:
    """Renderer interface for PDF engines."""

    name = "base"
    features: dict[str, bool] = {}

    def render(
        self,
        html_content: str,
        *,
        base_url: Optional[str],
        url_fetcher: Optional[Callable],
        config: dict[str, Any],
    ) -> bytes:
        raise NotImplementedError


class WeasyPrintRenderer(PdfRenderer):
    name = "weasyprint"
    features = {
        "url_fetcher": True,
        "page_stamps": True,
    }

    def render(
        self,
        html_content: str,
        *,
        base_url: Optional[str],
        url_fetcher: Optional[Callable],
        config: dict[str, Any],
    ) -> bytes:
        if not WEASYPRINT_AVAILABLE or not HTML:
            raise RuntimeError("WeasyPrint is not installed")
        return HTML(
            string=html_content,
            base_url=base_url,
            url_fetcher=url_fetcher,
        ).write_pdf()


class WkhtmltopdfRenderer(PdfRenderer):
    name = "wkhtmltopdf"
    features = {
        "url_fetcher": False,
        "page_stamps": False,
    }

    def render(
        self,
        html_content: str,
        *,
        base_url: Optional[str],
        url_fetcher: Optional[Callable],
        config: dict[str, Any],
    ) -> bytes:
        binary = shutil.which("wkhtmltopdf")
        if not binary:
            raise RuntimeError("wkhtmltopdf is not installed")

        args = [binary, "--quiet"]
        if config.get("wkhtmltopdf_allow_local", False):
            args.append("--enable-local-file-access")
        args += config.get("wkhtmltopdf_args", []) or []

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as html_file:
            html_file.write(html_content.encode("utf-8"))
            html_path = html_file.name
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as pdf_file:
            pdf_path = pdf_file.name

        try:
            subprocess.run(
                args + [html_path, pdf_path],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            with open(pdf_path, "rb") as handle:
                return handle.read()
        finally:
            for path in (html_path, pdf_path):
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    continue


_RENDERER_REGISTRY: dict[str, PdfRenderer] = {}


def register_pdf_renderer(name: str, renderer: PdfRenderer) -> None:
    _RENDERER_REGISTRY[name] = renderer


def get_pdf_renderer(name: Optional[str] = None) -> PdfRenderer:
    renderer_name = (name or _templating_renderer_name()).lower()
    renderer = _RENDERER_REGISTRY.get(renderer_name)
    if renderer:
        return renderer
    if "weasyprint" in _RENDERER_REGISTRY:
        return _RENDERER_REGISTRY["weasyprint"]
    raise RuntimeError(f"PDF renderer '{renderer_name}' is not available")


if WEASYPRINT_AVAILABLE:
    register_pdf_renderer("weasyprint", WeasyPrintRenderer())
register_pdf_renderer("wkhtmltopdf", WkhtmltopdfRenderer())


def _resolve_url_fetcher(base_url: Optional[str], override: Optional[Callable]) -> Optional[Callable]:
    if override:
        return override
    custom = _templating_settings().get("url_fetcher")
    if callable(custom):
        return custom
    return _build_safe_url_fetcher(base_url)


def _sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
    return cleaned or "document"


def _normalize_page_stamps(value: Any) -> Optional[dict[str, Any]]:
    if not value:
        return None
    if value is True:
        return {}
    if isinstance(value, str):
        return {"text": value}
    if isinstance(value, dict):
        return dict(value)
    return None


def _normalize_watermark(value: Any) -> Optional[dict[str, Any]]:
    if not value:
        return None
    if isinstance(value, str):
        return {"text": value}
    if isinstance(value, dict):
        return dict(value)
    return None


def _resolve_postprocess_config(
    config: Optional[dict[str, Any]],
    overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    defaults = _templating_postprocess_defaults()
    merged = _merge_dict(defaults, (config or {}).get("postprocess"))
    if overrides:
        merged.update(overrides)
    for key in ("watermark", "page_stamps", "encryption", "signature"):
        merged[key] = _merge_dict(
            defaults.get(key, {}), (config or {}).get("postprocess", {}).get(key)
        )
        if overrides and isinstance(overrides.get(key), dict):
            merged[key].update(overrides.get(key))
    return merged


def render_template_html(
    *,
    header_html: str,
    content_html: str,
    footer_html: str,
    config: dict[str, Any],
    postprocess: Optional[dict[str, Any]] = None,
) -> str:
    postprocess_config = _resolve_postprocess_config(config, postprocess)
    postprocess_enabled = bool(postprocess_config.get("enable", False))
    page_stamps = _normalize_page_stamps(
        (postprocess_config.get("page_stamps") if postprocess_enabled else None)
        or config.get("page_stamps")
    )
    watermark = _normalize_watermark(
        (postprocess_config.get("watermark") if postprocess_enabled else None)
        or config.get("watermark")
    )

    page_stamp_css = _build_page_stamp_css(page_stamps)
    watermark_html, watermark_css = _build_watermark_assets(watermark)
    if watermark_css:
        watermark_css += (
            ".pdf-header,.pdf-content,.pdf-footer{position:relative;z-index:1;}"
        )

    style_block = _build_style_block(
        config, extra_css_chunks=[page_stamp_css, watermark_css]
    )
    return (
        "<html><head><meta charset='utf-8'><style>"
        f"{style_block}"
        "</style></head><body>"
        f"{watermark_html}"
        f"<div class='pdf-header'>{header_html}</div>"
        f"<div class='pdf-content'>{content_html}</div>"
        f"<div class='pdf-footer'>{footer_html}</div>"
        "</body></html>"
    )


def render_pdf_from_html(
    html_content: str,
    *,
    config: Optional[dict[str, Any]] = None,
    base_url: Optional[str] = None,
    url_fetcher: Optional[Callable] = None,
    renderer: Optional[str] = None,
    postprocess: Optional[dict[str, Any]] = None,
) -> bytes:
    config = {**_default_template_config(), **(config or {})}
    base_url = base_url or str(settings.BASE_DIR)
    resolved_fetcher = _resolve_url_fetcher(base_url, url_fetcher)
    renderer_name = renderer or config.get("renderer")
    renderer_instance = get_pdf_renderer(renderer_name)
    pdf_bytes = renderer_instance.render(
        html_content,
        base_url=base_url,
        url_fetcher=resolved_fetcher,
        config=config,
    )
    return _apply_pdf_postprocessing(
        pdf_bytes, config=config, postprocess=postprocess
    )


def render_pdf(
    template: str,
    context: dict[str, Any],
    config: Optional[dict[str, Any]] = None,
    *,
    header_template: Optional[str] = None,
    footer_template: Optional[str] = None,
    base_url: Optional[str] = None,
    url_fetcher: Optional[Callable] = None,
    renderer: Optional[str] = None,
    postprocess: Optional[dict[str, Any]] = None,
) -> bytes:
    config = {**_default_template_config(), **(config or {})}
    header_path = _default_header() if header_template is None else header_template
    footer_path = _default_footer() if footer_template is None else footer_template
    header_html = _render_template(header_path, context)
    content_html = _render_template(template, context)
    footer_html = _render_template(footer_path, context)
    html_content = render_template_html(
        header_html=header_html,
        content_html=content_html,
        footer_html=footer_html,
        config=config,
        postprocess=postprocess,
    )
    return render_pdf_from_html(
        html_content,
        config=config,
        base_url=base_url,
        url_fetcher=url_fetcher,
        renderer=renderer or config.get("renderer"),
        postprocess=postprocess,
    )


class PdfBuilder:
    """Builder-style API for composing PDF templates dynamically."""

    def __init__(self) -> None:
        self._header_template: Optional[str] = None
        self._content_template: Optional[str] = None
        self._footer_template: Optional[str] = None
        self._header_html: Optional[str] = None
        self._content_html: Optional[str] = None
        self._footer_html: Optional[str] = None
        self._context: dict[str, Any] = {}
        self._config: dict[str, Any] = {}

    def header(self, template_path: Optional[str]) -> "PdfBuilder":
        self._header_template = template_path
        return self

    def content(self, template_path: Optional[str]) -> "PdfBuilder":
        self._content_template = template_path
        return self

    def footer(self, template_path: Optional[str]) -> "PdfBuilder":
        self._footer_template = template_path
        return self

    def header_html(self, html_content: str) -> "PdfBuilder":
        self._header_html = html_content
        return self

    def content_html(self, html_content: str) -> "PdfBuilder":
        self._content_html = html_content
        return self

    def footer_html(self, html_content: str) -> "PdfBuilder":
        self._footer_html = html_content
        return self

    def context(self, **kwargs: Any) -> "PdfBuilder":
        self._context.update(kwargs)
        return self

    def config(self, **kwargs: Any) -> "PdfBuilder":
        self._config.update(kwargs)
        return self

    def render(
        self,
        *,
        base_url: Optional[str] = None,
        url_fetcher: Optional[Callable] = None,
        renderer: Optional[str] = None,
        postprocess: Optional[dict[str, Any]] = None,
    ) -> bytes:
        config = {**_default_template_config(), **self._config}

        if self._content_html is not None:
            content_html = self._content_html
            if self._header_html is not None:
                header_html = self._header_html
            else:
                header_path = (
                    _default_header()
                    if self._header_template is None
                    else self._header_template
                )
                header_html = _render_template(header_path, self._context)
            if self._footer_html is not None:
                footer_html = self._footer_html
            else:
                footer_path = (
                    _default_footer()
                    if self._footer_template is None
                    else self._footer_template
                )
                footer_html = _render_template(footer_path, self._context)
        else:
            if not self._content_template:
                raise ValueError("content template is required")
            header_path = (
                _default_header()
                if self._header_template is None
                else self._header_template
            )
            footer_path = (
                _default_footer()
                if self._footer_template is None
                else self._footer_template
            )
            header_html = _render_template(header_path, self._context)
            content_html = _render_template(self._content_template, self._context)
            footer_html = _render_template(footer_path, self._context)

        html_content = render_template_html(
            header_html=header_html,
            content_html=content_html,
            footer_html=footer_html,
            config=config,
            postprocess=postprocess,
        )
        return render_pdf_from_html(
            html_content,
            config=config,
            base_url=base_url,
            url_fetcher=url_fetcher,
            renderer=renderer,
            postprocess=postprocess,
        )


def _resolve_pdf_permissions(permissions: Any) -> Any:
    """
    Convert permissions config to pypdf Permissions object if needed.

    Args:
        permissions: Dict, Permissions object, or None.

    Returns:
        pypdf Permissions object or None.
    """
    if permissions is None:
        return None

    # Already a Permissions object
    if hasattr(permissions, "print_document"):
        return permissions

    if not isinstance(permissions, dict):
        return None

    try:
        from pypdf import Permissions
    except ImportError:
        return None

    # Map common permission keys to Permissions constructor kwargs
    permission_mapping = {
        "print": "print_document",
        "print_document": "print_document",
        "modify": "modify",
        "copy": "extract",
        "extract": "extract",
        "add_annotations": "add_annotations",
        "annotations": "add_annotations",
        "fill_forms": "fill_form_fields",
        "fill_form_fields": "fill_form_fields",
        "extract_for_accessibility": "extract_text_and_graphics",
        "extract_text_and_graphics": "extract_text_and_graphics",
        "assemble": "assemble_document",
        "assemble_document": "assemble_document",
        "print_high_quality": "print_high_quality",
    }

    kwargs = {}
    for key, value in permissions.items():
        mapped_key = permission_mapping.get(str(key).lower())
        if mapped_key:
            kwargs[mapped_key] = bool(value)

    return Permissions(**kwargs) if kwargs else None


def _apply_pdf_encryption(
    pdf_bytes: bytes, encryption: dict[str, Any], *, strict: bool
) -> bytes:
    if not encryption:
        return pdf_bytes
    if not PYPDF_AVAILABLE or not PdfReader or not PdfWriter:
        if strict:
            raise RuntimeError("pypdf is required for PDF encryption")
        return pdf_bytes

    user_password = encryption.get("user_password") or encryption.get("password") or ""
    owner_password = encryption.get("owner_password")
    permissions = _resolve_pdf_permissions(encryption.get("permissions"))

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    if reader.metadata:
        writer.add_metadata(dict(reader.metadata))

    encrypt_kwargs: dict[str, Any] = {"owner_password": owner_password}
    if permissions is not None:
        encrypt_kwargs["permissions"] = permissions

    writer.encrypt(user_password, **encrypt_kwargs)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _load_watermark_pdf_bytes(
    watermark: dict[str, Any], *, config: dict[str, Any]
) -> Optional[bytes]:
    if watermark.get("pdf_bytes"):
        return watermark.get("pdf_bytes")
    pdf_path = watermark.get("pdf_path")
    if pdf_path:
        try:
            with open(pdf_path, "rb") as handle:
                return handle.read()
        except OSError:
            return None
    if watermark.get("text") and WEASYPRINT_AVAILABLE and HTML:
        page_size = config.get("page_size", "A4")
        orientation = config.get("orientation", "portrait")
        text = html.escape(str(watermark.get("text")))
        watermark_html = (
            "<html><head><style>"
            f"@page {{ size: {page_size} {orientation}; margin: 0; }}"
            "body { margin: 0; }"
            ".wm { position: fixed; top: 50%; left: 50%;"
            " transform: translate(-50%, -50%) rotate(-30deg);"
            " font-size: 48pt; color: #999999; opacity: 0.15;"
            " }"
            "</style></head>"
            f"<body><div class='wm'>{text}</div></body></html>"
        )
        return HTML(string=watermark_html).write_pdf()
    return None


def _apply_pdf_watermark_overlay(
    pdf_bytes: bytes, watermark: dict[str, Any], *, config: dict[str, Any], strict: bool
) -> bytes:
    if not watermark or watermark.get("mode", "css") != "overlay":
        return pdf_bytes
    if not PYPDF_AVAILABLE or not PdfReader or not PdfWriter:
        if strict:
            raise RuntimeError("pypdf is required for PDF watermark overlays")
        return pdf_bytes

    watermark_pdf = _load_watermark_pdf_bytes(watermark, config=config)
    if not watermark_pdf:
        return pdf_bytes

    reader = PdfReader(io.BytesIO(pdf_bytes))
    watermark_reader = PdfReader(io.BytesIO(watermark_pdf))
    watermark_page = watermark_reader.pages[0]
    writer = PdfWriter()
    for page in reader.pages:
        page.merge_page(watermark_page)
        writer.add_page(page)
    if reader.metadata:
        writer.add_metadata(dict(reader.metadata))
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _apply_pdf_signature(
    pdf_bytes: bytes, signature: dict[str, Any], *, strict: bool
) -> bytes:
    if not signature:
        return pdf_bytes
    handler = signature.get("handler")
    if callable(handler):
        return handler(pdf_bytes)

    pfx_path = signature.get("pfx_path")
    if not pfx_path:
        if strict:
            raise RuntimeError("Signature configuration requires a handler or pfx_path")
        return pdf_bytes
    try:
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers
    except ImportError:
        if strict:
            raise RuntimeError("pyhanko is required for PDF signing")
        return pdf_bytes

    passphrase = signature.get("pfx_password")
    if isinstance(passphrase, str):
        passphrase = passphrase.encode("utf-8")
    signer = signers.SimpleSigner.load_pkcs12(pfx_path, passphrase=passphrase)
    field_name = signature.get("field_name", "Signature1")
    reason = signature.get("reason")
    location = signature.get("location")
    contact_info = signature.get("contact_info")
    signature_meta = signers.PdfSignatureMetadata(
        field_name=field_name,
        reason=reason,
        location=location,
        contact_info=contact_info,
    )
    output = io.BytesIO()
    signers.sign_pdf(
        IncrementalPdfFileWriter(io.BytesIO(pdf_bytes)),
        signature_meta,
        signer=signer,
        output=output,
    )
    return output.getvalue()


def _apply_pdf_postprocessing(
    pdf_bytes: bytes,
    *,
    config: Optional[dict[str, Any]] = None,
    postprocess: Optional[dict[str, Any]] = None,
) -> bytes:
    config = config or {}
    postprocess_config = _resolve_postprocess_config(config, postprocess)
    if not postprocess_config.get("enable", False):
        return pdf_bytes

    strict = bool(postprocess_config.get("strict", True))
    result = _apply_pdf_watermark_overlay(
        pdf_bytes,
        postprocess_config.get("watermark") or {},
        config=config,
        strict=strict,
    )
    result = _apply_pdf_encryption(
        result, postprocess_config.get("encryption") or {}, strict=strict
    )
    result = _apply_pdf_signature(
        result, postprocess_config.get("signature") or {}, strict=strict
    )
    return result


def _cache_settings_for_template(template_def: TemplateDefinition) -> dict[str, Any]:
    overrides = {}
    if isinstance(template_def.config, dict):
        overrides = template_def.config.get("cache") or {}
    return _merge_dict(_templating_cache(), overrides)


def _hash_payload(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _build_pdf_cache_key(
    template_def: TemplateDefinition,
    *,
    pk: Optional[str],
    user: Optional[Any],
    client_data: dict[str, Any],
    cache_settings: dict[str, Any],
) -> Optional[str]:
    if not cache_settings.get("enable", False):
        return None

    payload: dict[str, Any] = {"template": template_def.url_path, "pk": pk}
    if cache_settings.get("vary_on_user", True):
        payload["user"] = getattr(user, "id", None) or "anon"
    if cache_settings.get("vary_on_client_data", True):
        payload["client_data"] = client_data or {}
    if cache_settings.get("vary_on_template_config", True):
        payload["config"] = template_def.config
    payload["renderer"] = template_def.config.get("renderer") or _templating_renderer_name()

    key_prefix = cache_settings.get("key_prefix", "rail:pdf_cache")
    return f"{key_prefix}:{_hash_payload(payload)}"


def _pdf_job_cache_key(job_id: str) -> str:
    return f"rail:pdf_job:{job_id}"


def _pdf_job_payload_key(job_id: str) -> str:
    return f"rail:pdf_job_payload:{job_id}"


def _get_pdf_storage_dir(async_settings: dict[str, Any]) -> Path:
    storage_dir = async_settings.get("storage_dir")
    if storage_dir:
        path = Path(str(storage_dir))
    elif getattr(settings, "MEDIA_ROOT", None):
        path = Path(settings.MEDIA_ROOT) / "rail_pdfs"
    else:
        path = Path(tempfile.gettempdir()) / "rail_pdfs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_pdf_job(job_id: str) -> Optional[dict[str, Any]]:
    return cache.get(_pdf_job_cache_key(job_id))


def _set_pdf_job(job_id: str, job: dict[str, Any], *, timeout: int) -> None:
    cache.set(_pdf_job_cache_key(job_id), job, timeout=timeout)


def _update_pdf_job(
    job_id: str, updates: dict[str, Any], *, timeout: int
) -> Optional[dict[str, Any]]:
    job = _get_pdf_job(job_id)
    if not job:
        return None
    job.update(updates)
    _set_pdf_job(job_id, job, timeout=timeout)
    return job


def _delete_pdf_job(job_id: str) -> None:
    cache.delete(_pdf_job_cache_key(job_id))
    cache.delete(_pdf_job_payload_key(job_id))


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _job_access_allowed(request: Any, job: dict[str, Any]) -> bool:
    user = _resolve_request_user(request)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    owner_id = job.get("owner_id")
    return bool(owner_id and str(owner_id) == str(getattr(user, "id", "")))


def _notify_pdf_job_webhook(
    job: dict[str, Any], async_settings: dict[str, Any]
) -> None:
    webhook_url = async_settings.get("webhook_url")
    if not webhook_url:
        return
    try:
        import requests
    except Exception:
        logger.warning("requests is unavailable; cannot post PDF webhook")
        return
    headers = async_settings.get("webhook_headers") or {}
    timeout = int(async_settings.get("webhook_timeout_seconds", 10))
    try:
        requests.post(webhook_url, json=job, headers=headers, timeout=timeout)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Failed to notify PDF webhook: %s", exc)


def _build_job_request(owner_id: Optional[Any]) -> HttpRequest:
    request = HttpRequest()
    user = None
    if owner_id:
        try:
            user_model = get_user_model()
            user = user_model.objects.filter(pk=owner_id).first()
        except Exception:
            user = None
    request.user = user or AnonymousUser()
    return request


def _run_pdf_job(job_id: str) -> None:
    job = _get_pdf_job(job_id)
    if not job:
        return

    async_settings = _templating_async()
    timeout = int(async_settings.get("expires_seconds", 3600))
    payload = cache.get(_pdf_job_payload_key(job_id))
    if not payload:
        _update_pdf_job(
            job_id, {"status": "failed", "error": "Missing job payload"}, timeout=timeout
        )
        return

    _update_pdf_job(
        job_id,
        {"status": "running", "started_at": timezone.now().isoformat()},
        timeout=timeout,
    )

    template_path = payload.get("template_path")
    template_def = template_registry.get(str(template_path))
    if not template_def:
        _update_pdf_job(
            job_id, {"status": "failed", "error": "Template not found"}, timeout=timeout
        )
        return

    pk = payload.get("pk")
    instance: Optional[models.Model] = None
    if template_def.model:
        try:
            instance = template_def.model.objects.get(pk=pk)
        except (template_def.model.DoesNotExist, ValidationError, ValueError, TypeError):
            _update_pdf_job(
                job_id,
                {"status": "failed", "error": "Instance not found"},
                timeout=timeout,
            )
            return

    request = _build_job_request(job.get("owner_id"))
    client_data = payload.get("client_data") or {}
    setattr(request, "rail_template_client_data", client_data)
    context = _build_template_context(
        request, instance, template_def, client_data, pk=str(pk) if pk else None
    )

    try:
        pdf_bytes = render_pdf(
            template_def.content_template,
            context,
            config=template_def.config,
            header_template=template_def.header_template,
            footer_template=template_def.footer_template,
            base_url=payload.get("base_url"),
            renderer=payload.get("renderer"),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Async PDF job failed: %s", exc)
        _update_pdf_job(
            job_id,
            {"status": "failed", "error": str(exc) if _templating_expose_errors() else "PDF render failed"},
            timeout=timeout,
        )
        _notify_pdf_job_webhook(_get_pdf_job(job_id) or job, async_settings)
        return

    storage_dir = _get_pdf_storage_dir(async_settings)
    filename = payload.get("filename") or template_def.url_path.replace("/", "-")
    filename = _sanitize_filename(filename)
    file_path = storage_dir / f"{job_id}.pdf"
    try:
        with open(file_path, "wb") as handle:
            handle.write(pdf_bytes)
    except OSError as exc:
        _update_pdf_job(
            job_id,
            {"status": "failed", "error": f"Failed to persist PDF: {exc}"},
            timeout=timeout,
        )
        _notify_pdf_job_webhook(_get_pdf_job(job_id) or job, async_settings)
        return

    _update_pdf_job(
        job_id,
        {
            "status": "completed",
            "completed_at": timezone.now().isoformat(),
            "file_path": str(file_path),
            "content_type": "application/pdf",
            "filename": f"{filename}.pdf",
        },
        timeout=timeout,
    )
    _notify_pdf_job_webhook(_get_pdf_job(job_id) or job, async_settings)


try:
    from celery import shared_task
except Exception:  # pragma: no cover - optional dependency
    shared_task = None

if shared_task:
    @shared_task(name="rail_django.pdf_job")
    def pdf_job_task(job_id: str) -> None:
        _run_pdf_job(job_id)
else:
    pdf_job_task = None


def generate_pdf_async(
    *,
    request: HttpRequest,
    template_def: TemplateDefinition,
    pk: Optional[str],
    client_data: dict[str, Any],
    base_url: Optional[str] = None,
    renderer: Optional[str] = None,
) -> dict[str, Any]:
    async_settings = _templating_async()
    backend = str(async_settings.get("backend", "thread")).lower()
    expires_seconds = int(async_settings.get("expires_seconds", 3600))

    job_id = str(uuid.uuid4())
    now = timezone.now()
    owner = _resolve_request_user(request)
    job = {
        "id": job_id,
        "status": "pending",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=expires_seconds)).isoformat(),
        "owner_id": getattr(owner, "id", None),
    }

    payload = {
        "template_path": template_def.url_path,
        "pk": pk,
        "client_data": client_data,
        "base_url": base_url,
        "renderer": renderer,
        "filename": template_def.title,
    }

    _set_pdf_job(job_id, job, timeout=expires_seconds)
    cache.set(_pdf_job_payload_key(job_id), payload, timeout=expires_seconds)

    if backend == "thread":
        thread = threading.Thread(target=_run_pdf_job, args=(job_id,), daemon=True)
        thread.start()
    elif backend == "celery":
        if not pdf_job_task:
            _update_pdf_job(
                job_id,
                {"status": "failed", "error": "Celery is not available"},
                timeout=expires_seconds,
            )
            raise RuntimeError("Celery backend not available")
        pdf_job_task.delay(job_id)
    elif backend == "rq":
        try:
            import django_rq
        except Exception as exc:
            _update_pdf_job(
                job_id,
                {"status": "failed", "error": "RQ is not available"},
                timeout=expires_seconds,
            )
            raise RuntimeError("RQ backend not available") from exc
        queue_name = async_settings.get("queue", "default")
        queue = django_rq.get_queue(queue_name)
        queue.enqueue(_run_pdf_job, job_id)
    else:
        _update_pdf_job(
            job_id,
            {"status": "failed", "error": "Unknown async backend"},
            timeout=expires_seconds,
        )
        raise RuntimeError("Unknown async backend")

    status_path = f"/api/{_url_prefix().rstrip('/')}/jobs/{job_id}/"
    download_path = f"/api/{_url_prefix().rstrip('/')}/jobs/{job_id}/download/"
    return {
        "job_id": job_id,
        "status": "pending",
        "status_url": request.build_absolute_uri(status_path),
        "download_url": request.build_absolute_uri(download_path),
        "expires_in": expires_seconds,
    }


def _cleanup_pdf_job_files(job: dict[str, Any]) -> None:
    file_path = job.get("file_path")
    if not file_path:
        return
    try:
        Path(str(file_path)).unlink(missing_ok=True)
    except Exception:
        return


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(
    jwt_required if jwt_required else (lambda view: view), name="dispatch"
)
class PdfTemplateView(View):
    """Serve model PDFs rendered with WeasyPrint."""

    http_method_names = ["get"]

    def get(
        self,
        request: HttpRequest,
        template_path: str,
        pk: str,
        *args: Any,
        **kwargs: Any,
    ) -> HttpResponse:
        """
        Render a PDF for a given model instance.

        Args:
            request: Incoming Django request.
            template_path: Relative template path registered for the model.
            pk: Primary key of the model instance to render.

        Returns:
            PDF response or JSON error when unavailable.
        """
        template_def = template_registry.get(template_path)
        if not template_def:
            self._log_template_event(
                request,
                success=False,
                error_message="Template not found",
                template_path=template_path,
                pk=pk,
            )
            return JsonResponse(
                {"error": "Template not found", "template": template_path}, status=404
            )

        renderer_name = template_def.config.get("renderer") or _templating_renderer_name()
        try:
            get_pdf_renderer(str(renderer_name))
        except Exception as exc:
            self._log_template_event(
                request,
                success=False,
                error_message=str(exc),
                template_def=template_def,
                template_path=template_path,
                pk=pk,
            )
            return JsonResponse(
                {
                    "error": "PDF renderer unavailable",
                    "detail": str(exc) if _templating_expose_errors() else None,
                },
                status=500,
            )

        rate_limit_response = self._check_rate_limit(request, template_def)
        if rate_limit_response:
            return rate_limit_response

        instance: Optional[models.Model] = None
        if template_def.model:
            try:
                instance = template_def.model.objects.get(pk=pk)
            except template_def.model.DoesNotExist:
                self._log_template_event(
                    request,
                    success=False,
                    error_message="Instance not found",
                    template_def=template_def,
                    template_path=template_path,
                    pk=pk,
                )
                return JsonResponse(
                    {
                        "error": "Instance not found",
                        "model": template_def.model._meta.label,
                        "pk": pk,
                    },
                    status=404,
                )
            except (ValidationError, ValueError, TypeError):
                self._log_template_event(
                    request,
                    success=False,
                    error_message="Invalid primary key",
                    template_def=template_def,
                    template_path=template_path,
                    pk=pk,
                )
                return JsonResponse(
                    {"error": "Invalid primary key", "pk": pk}, status=400
                )

        denial = self._authorize_template_access(request, template_def, instance)
        if denial:
            self._log_template_event(
                request,
                success=False,
                error_message="Forbidden",
                template_def=template_def,
                template_path=template_path,
                pk=pk,
            )
            return denial

        client_data = _extract_client_data(request, template_def)
        setattr(request, "rail_template_client_data", client_data)

        if self._parse_async_request(request):
            async_settings = _templating_async()
            if not async_settings.get("enable", False):
                return JsonResponse(
                    {"error": "Async PDF jobs are disabled"}, status=400
                )
            try:
                job_payload = generate_pdf_async(
                    request=request,
                    template_def=template_def,
                    pk=pk,
                    client_data=client_data,
                    base_url=self._resolve_base_url(request, template_def),
                    renderer=renderer_name,
                )
            except Exception as exc:
                return JsonResponse(
                    {
                        "error": "Failed to enqueue PDF job",
                        "detail": str(exc) if _templating_expose_errors() else None,
                    },
                    status=500,
                )
            self._log_template_event(
                request,
                success=True,
                template_def=template_def,
                template_path=template_path,
                pk=pk,
            )
            return JsonResponse(job_payload, status=202)

        cache_settings = _cache_settings_for_template(template_def)
        cache_key = _build_pdf_cache_key(
            template_def,
            pk=pk,
            user=self._resolve_request_user(request),
            client_data=client_data,
            cache_settings=cache_settings,
        )
        if cache_key:
            cached_pdf = cache.get(cache_key)
            if cached_pdf:
                response = HttpResponse(cached_pdf, content_type="application/pdf")
                filename = self._resolve_filename(template_def, pk)
                response["Content-Disposition"] = f'inline; filename="{filename}"'
                self._log_template_event(
                    request,
                    success=True,
                    template_def=template_def,
                    template_path=template_path,
                    pk=pk,
                )
                return response

        context = self._build_context(request, instance, template_def, client_data, pk)

        try:
            pdf_bytes = self._render_pdf(
                template_def,
                context,
                base_url=self._resolve_base_url(request, template_def),
                renderer=renderer_name,
            )
        except Exception as exc:  # pragma: no cover - defensive logging branch
            model_name = (
                template_def.model.__name__
                if template_def.model
                else template_def.url_path
            )
            logger.exception(
                "Failed to render PDF for %s pk=%s: %s",
                model_name,
                pk,
                exc,
            )
            self._log_template_event(
                request,
                success=False,
                error_message=str(exc),
                template_def=template_def,
                template_path=template_path,
                pk=pk,
            )
            detail = str(exc) if _templating_expose_errors() else "Failed to render PDF"
            return JsonResponse(
                {"error": "Failed to render PDF", "detail": detail}, status=500
            )

        if cache_key:
            cache_timeout = int(cache_settings.get("timeout_seconds", 300))
            cache.set(cache_key, pdf_bytes, timeout=cache_timeout)

        filename = self._resolve_filename(template_def, pk)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        self._log_template_event(
            request,
            success=True,
            template_def=template_def,
            template_path=template_path,
            pk=pk,
        )
        return response

    def _build_context(
        self,
        request: HttpRequest,
        instance: Optional[models.Model],
        template_def: TemplateDefinition,
        client_data: Optional[dict[str, Any]] = None,
        pk: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Build template context combining the model instance and method payload.

        Args:
            request: Incoming request.
            instance: Model instance resolved by pk.
            template_def: Template definition holding the method to call.

        Returns:
            Context dictionary for rendering.
        """
        return _build_template_context(
            request,
            instance,
            template_def,
            client_data,
            pk=pk,
        )

    def _authorize_template_access(
        self,
        request: HttpRequest,
        template_def: TemplateDefinition,
        instance: Optional[models.Model],
    ) -> Optional[JsonResponse]:
        """
        Apply RBAC and permission requirements before rendering the PDF.
        """
        return authorize_template_access(request, template_def, instance)

    def _parse_async_request(self, request: HttpRequest) -> bool:
        value = request.GET.get("async")
        if value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _resolve_base_url(
        self, request: HttpRequest, template_def: TemplateDefinition
    ) -> str:
        base_url = template_def.config.get("base_url")
        if base_url:
            return str(base_url)
        settings_base_url = _templating_settings().get("base_url")
        if settings_base_url == "request":
            return request.build_absolute_uri("/")
        if settings_base_url:
            return str(settings_base_url)
        return str(settings.BASE_DIR)

    def _resolve_filename(self, template_def: TemplateDefinition, pk: Optional[str]) -> str:
        if template_def.model:
            base_name = f"{template_def.model._meta.model_name}-{pk}"
        else:
            base_name = f"{template_def.url_path.replace('/', '-')}-{pk}"
        return f"{_sanitize_filename(base_name)}.pdf"

    def _get_rate_limit_identifier(
        self, request: HttpRequest, rate_limit: dict[str, Any]
    ) -> str:
        user = _resolve_request_user(request)
        if user and getattr(user, "is_authenticated", False):
            return f"user:{user.id}"

        trusted_proxies = rate_limit.get("trusted_proxies") or []
        remote_addr = request.META.get("REMOTE_ADDR", "")
        ip_address = remote_addr or "unknown"

        if self._is_trusted_proxy(remote_addr, trusted_proxies):
            forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
            if forwarded_for:
                ip_address = forwarded_for.split(",")[0].strip()

        return f"ip:{ip_address}"

    def _is_trusted_proxy(self, remote_addr: str, trusted_proxies: Iterable[str]) -> bool:
        if not remote_addr:
            return False
        for proxy in trusted_proxies:
            proxy = str(proxy).strip()
            if not proxy:
                continue
            if "/" in proxy:
                try:
                    if ipaddress.ip_address(remote_addr) in ipaddress.ip_network(
                        proxy, strict=False
                    ):
                        return True
                except ValueError:
                    continue
            if remote_addr == proxy:
                return True
        return False

    def _check_rate_limit(
        self, request: HttpRequest, template_def: TemplateDefinition
    ) -> Optional[JsonResponse]:
        config = _templating_rate_limit()
        overrides = template_def.config.get("rate_limit") or {}
        config = _merge_dict(config, overrides)
        if not config.get("enable", True):
            return None

        window_seconds = int(config.get("window_seconds", 60))
        max_requests = int(config.get("max_requests", 30))
        identifier = self._get_rate_limit_identifier(request, config)
        cache_key = f"rail:pdf_rl:{identifier}:{template_def.url_path}"

        # Atomic increment with race-condition handling
        # Try to increment first; if key doesn't exist, add will set it
        try:
            current_count = cache.incr(cache_key)
        except ValueError:
            # Key doesn't exist, try to add it atomically
            if cache.add(cache_key, 1, timeout=window_seconds):
                return None
            # Another request beat us to it, try increment again
            try:
                current_count = cache.incr(cache_key)
            except ValueError:
                # Key expired between add and incr, start fresh
                cache.set(cache_key, 1, timeout=window_seconds)
                return None

        if current_count > max_requests:
            return JsonResponse(
                {"error": "Rate limit exceeded", "retry_after": window_seconds},
                status=429,
            )

        return None

    def _resolve_request_user(self, request: HttpRequest):
        """
        Retrieve a user from the request session or Authorization header.
        """
        return _resolve_request_user(request)

    def _render_pdf(
        self,
        template_def: TemplateDefinition,
        context: dict[str, Any],
        *,
        base_url: Optional[str] = None,
        renderer: Optional[str] = None,
    ) -> bytes:
        """
        Render the PDF bytes using the configured renderer.

        Args:
            template_def: Template definition with paths/config.
            context: Context for rendering.

        Returns:
            PDF as bytes.
        """
        renderer_name = renderer or template_def.config.get("renderer")
        renderer_name = str(renderer_name or _templating_renderer_name())

        if renderer_name.lower() == "weasyprint":
            if PYDYF_VERSION and Version:
                try:
                    if Version(PYDYF_VERSION) < Version("0.11.0"):
                        raise RuntimeError(
                            f"Incompatible pydyf version {PYDYF_VERSION}; "
                            "install pydyf>=0.11.0 to render PDFs."
                        )
                except InvalidVersion:
                    pass
            _patch_pydyf_pdf()

        return render_pdf(
            template_def.content_template,
            context,
            config=template_def.config,
            header_template=template_def.header_template,
            footer_template=template_def.footer_template,
            base_url=base_url,
            renderer=renderer_name,
        )

    def _log_template_event(
        self,
        request: HttpRequest,
        *,
        success: bool,
        error_message: Optional[str] = None,
        template_def: Optional[TemplateDefinition] = None,
        template_path: Optional[str] = None,
        pk: Optional[str] = None,
    ) -> None:
        """Log an audit event for template rendering."""
        if not log_audit_event or not AuditEventType:
            return

        details = {
            "action": "template_render",
            "template_path": template_path,
            "pk": pk,
        }
        if template_def:
            if template_def.model:
                details["model"] = template_def.model._meta.label
            details["title"] = template_def.title
            details["source"] = template_def.source

        log_audit_event(
            request,
            AuditEventType.DATA_ACCESS,
            success=success,
            error_message=error_message,
            additional_data=details,
        )


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(
    jwt_required if jwt_required else (lambda view: view), name="dispatch"
)
class PdfTemplatePreviewView(View):
    """Render HTML previews for PDF templates."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, template_path: str, pk: str) -> HttpResponse:
        if not _templating_preview_enabled():
            raise Http404("Preview disabled")

        template_def = template_registry.get(template_path)
        if not template_def:
            raise Http404("Template not found")

        instance: Optional[models.Model] = None
        if template_def.model:
            try:
                instance = template_def.model.objects.get(pk=pk)
            except (template_def.model.DoesNotExist, ValidationError, ValueError, TypeError):
                raise Http404("Instance not found")

        denial = authorize_template_access(request, template_def, instance)
        if denial:
            return denial

        client_data = _extract_client_data(request, template_def)
        context = _build_template_context(
            request, instance, template_def, client_data, pk=pk
        )
        header_html = _render_template(template_def.header_template, context)
        content_html = _render_template(template_def.content_template, context)
        footer_html = _render_template(template_def.footer_template, context)
        html_content = render_template_html(
            header_html=header_html,
            content_html=content_html,
            footer_html=footer_html,
            config=template_def.config,
        )
        return HttpResponse(html_content, content_type="text/html")


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(
    jwt_required if jwt_required else (lambda view: view), name="dispatch"
)
class PdfTemplateCatalogView(View):
    """Expose template catalog metadata for UI-driven workflows."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest) -> JsonResponse:
        catalog_settings = _templating_catalog()
        if not catalog_settings.get("enable", True):
            raise Http404("Catalog disabled")

        user = _resolve_request_user(request)
        if catalog_settings.get("require_authentication", True) and not (
            user and getattr(user, "is_authenticated", False)
        ):
            return JsonResponse(
                {"error": "Authentication required"}, status=401
            )

        include_config = bool(catalog_settings.get("include_config", False))
        include_permissions = bool(catalog_settings.get("include_permissions", True))
        filter_by_access = bool(catalog_settings.get("filter_by_access", True))

        templates = []
        for url_path, template_def in sorted(template_registry.all().items()):
            access = evaluate_template_access(template_def, user=user, instance=None)
            if filter_by_access and not access.allowed:
                continue

            entry = {
                "url_path": url_path,
                "title": template_def.title,
                "source": template_def.source,
                "model": template_def.model._meta.label if template_def.model else None,
                "require_authentication": template_def.require_authentication,
                "allow_client_data": template_def.allow_client_data,
                "client_data_schema": template_def.client_data_schema,
            }
            if include_permissions:
                entry.update(
                    {
                        "roles": template_def.roles,
                        "permissions": template_def.permissions,
                        "guard": template_def.guard,
                    }
                )
            if include_config:
                entry["config"] = template_def.config
            if not filter_by_access:
                entry["access"] = {
                    "allowed": access.allowed,
                    "reason": access.reason,
                    "status_code": access.status_code,
                }
            templates.append(entry)

        return JsonResponse({"templates": templates})


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(
    jwt_required if jwt_required else (lambda view: view), name="dispatch"
)
class PdfTemplateJobStatusView(View):
    """Return status for async PDF jobs."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, job_id: str) -> JsonResponse:
        job = _get_pdf_job(str(job_id))
        if not job:
            raise Http404("PDF job not found")

        # Check expiration before access check to prevent unauthorized users
        # from keeping jobs alive by polling
        expires_at = _parse_iso_datetime(job.get("expires_at"))
        if expires_at and expires_at <= timezone.now():
            _cleanup_pdf_job_files(job)
            _delete_pdf_job(str(job_id))
            raise Http404("PDF job not found")

        if not _job_access_allowed(request, job):
            return JsonResponse({"error": "PDF job not permitted"}, status=403)

        payload = {
            "job_id": job.get("id"),
            "status": job.get("status"),
            "error": job.get("error"),
            "created_at": job.get("created_at"),
            "completed_at": job.get("completed_at"),
            "expires_at": job.get("expires_at"),
        }
        if job.get("status") == "completed":
            download_path = f"/api/{_url_prefix().rstrip('/')}/jobs/{job_id}/download/"
            payload["download_url"] = request.build_absolute_uri(download_path)

        return JsonResponse(payload)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(
    jwt_required if jwt_required else (lambda view: view), name="dispatch"
)
class PdfTemplateJobDownloadView(View):
    """Download completed PDF job files."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, job_id: str) -> HttpResponse:
        job = _get_pdf_job(str(job_id))
        if not job:
            raise Http404("PDF job not found")

        # Check expiration before access check to prevent unauthorized users
        # from keeping jobs alive by polling
        expires_at = _parse_iso_datetime(job.get("expires_at"))
        if expires_at and expires_at <= timezone.now():
            _cleanup_pdf_job_files(job)
            _delete_pdf_job(str(job_id))
            raise Http404("PDF job not found")

        if not _job_access_allowed(request, job):
            return JsonResponse({"error": "PDF job not permitted"}, status=403)

        if job.get("status") != "completed":
            return JsonResponse({"error": "PDF job not completed"}, status=409)

        file_path = job.get("file_path")
        if not file_path or not Path(str(file_path)).exists():
            return JsonResponse({"error": "PDF job file missing"}, status=410)

        filename = _sanitize_filename(str(job.get("filename") or "document"))
        response = FileResponse(
            open(file_path, "rb"),
            content_type=job.get("content_type", "application/pdf"),
        )
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response

def template_urlpatterns():
    """
    Return URL patterns to expose template endpoints under the configured prefix.

    The final URL shape is:
        /api/<prefix>/<template_path>/<pk>/

    Where <template_path> defaults to <app_label>/<model_name>/<function_name>.
    """
    prefix = _url_prefix().rstrip("/")
    return [
        path(
            f"{prefix}/catalog/",
            PdfTemplateCatalogView.as_view(),
            name="pdf_template_catalog",
        ),
        path(
            f"{prefix}/preview/<path:template_path>/<str:pk>/",
            PdfTemplatePreviewView.as_view(),
            name="pdf_template_preview",
        ),
        path(
            f"{prefix}/jobs/<uuid:job_id>/",
            PdfTemplateJobStatusView.as_view(),
            name="pdf_template_job_status",
        ),
        path(
            f"{prefix}/jobs/<uuid:job_id>/download/",
            PdfTemplateJobDownloadView.as_view(),
            name="pdf_template_job_download",
        ),
        path(
            f"{prefix}/<path:template_path>/<str:pk>/",
            PdfTemplateView.as_view(),
            name="pdf_template",
        )
    ]


__all__ = [
    "PdfTemplateView",
    "PdfTemplatePreviewView",
    "PdfTemplateCatalogView",
    "PdfTemplateJobStatusView",
    "PdfTemplateJobDownloadView",
    "model_pdf_template",
    "pdf_template",
    "template_registry",
    "template_urlpatterns",
    "evaluate_template_access",
    "authorize_template_access",
    "render_pdf",
    "render_pdf_from_html",
    "render_template_html",
    "PdfBuilder",
    "PdfRenderer",
    "register_pdf_renderer",
    "get_pdf_renderer",
    "generate_pdf_async",
]
