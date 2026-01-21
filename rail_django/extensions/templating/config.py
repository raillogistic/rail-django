"""
Configuration and settings helpers for the PDF templating system.

This module provides default configuration values and helper functions
to read and merge settings from Django's settings module.
"""

import inspect
import logging
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import unquote, urljoin, urlparse

from django.conf import settings

logger = logging.getLogger(__name__)

# Optional WeasyPrint URL fetcher
try:
    from weasyprint.urls import default_url_fetcher

    WEASYPRINT_URL_FETCHER_AVAILABLE = True
except ImportError:
    default_url_fetcher = None
    WEASYPRINT_URL_FETCHER_AVAILABLE = False

# Optional pydyf version guard (WeasyPrint 61.x expects >=0.11.0)
try:
    import pydyf  # type: ignore
    from packaging.version import InvalidVersion, Version

    PYDYF_VERSION = getattr(pydyf, "__version__", "0.0.0")
except ImportError:
    pydyf = None
    PYDYF_VERSION = None
    Version = None
    InvalidVersion = None

# ---------------------------------------------------------------------------
# Default configuration dictionaries
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Settings accessor functions
# ---------------------------------------------------------------------------


def _merge_dict(defaults: dict[str, Any], overrides: Any) -> dict[str, Any]:
    """Shallow-merge dict settings with safe fallbacks."""
    merged = dict(defaults)
    if isinstance(overrides, dict):
        merged.update(overrides)
    return merged


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


# ---------------------------------------------------------------------------
# File roots and URL fetcher helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Pydyf compatibility patch
# ---------------------------------------------------------------------------


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
    except (TypeError, ValueError):
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


# ---------------------------------------------------------------------------
# Postprocess config resolution
# ---------------------------------------------------------------------------


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


def _resolve_url_fetcher(
    base_url: Optional[str], override: Optional[Callable]
) -> Optional[Callable]:
    if override:
        return override
    custom = _templating_settings().get("url_fetcher")
    if callable(custom):
        return custom
    return _build_safe_url_fetcher(base_url)
