"""
Template registry and decorators for PDF templating.

This module provides the TemplateRegistry class that tracks all registered
PDF templates, along with the @model_pdf_template and @pdf_template decorators
for registering templates on model methods or standalone functions.
"""

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Sequence, Type

from django.db import models
from django.db.models.signals import class_prepared

from .config import (
    _default_footer,
    _default_header,
    _default_template_config,
    _url_prefix,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Template Registry
# ---------------------------------------------------------------------------


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


# Global registry instance
template_registry = TemplateRegistry()


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Signal handler for model registration
# ---------------------------------------------------------------------------


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
    except Exception as exc:
        logger.debug("Skipping eager template registration: %s", exc)


_register_existing_models_if_ready()
