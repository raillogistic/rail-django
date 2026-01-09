"""
PDF templating helpers built on top of WeasyPrint.

This module lets models expose printable PDFs by decorating a model method with
`@model_pdf_template`. The decorator registers a dynamic Django view that:
- Finds the related model instance (by PK passed in the URL)
- Renders header/content/footer templates with the instance context and the
  return value of the decorated method
- Applies optional style configuration (margins, fonts, spacing, etc.)
- Streams the generated PDF with WeasyPrint

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

import logging
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Optional, Sequence

from django.conf import settings
from django.db import models
from django.db.models.signals import class_prepared
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.template import loader
from django.urls import path
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except ImportError:
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


def _templating_settings() -> Dict[str, Any]:
    """
    Safely read the templating defaults from settings.

    Returns:
        A dictionary with header/footer defaults and style defaults.
    """
    return getattr(settings, "RAIL_DJANGO_GRAPHQL_TEMPLATING", {})


def _default_template_config() -> Dict[str, str]:
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


@dataclass
class TemplateMeta:
    """Raw decorator metadata attached to a model method."""

    header_template: Optional[str]
    content_template: str
    footer_template: Optional[str]
    url_path: Optional[str]
    config: Dict[str, Any] = field(default_factory=dict)
    roles: Sequence[str] = field(default_factory=tuple)
    permissions: Sequence[str] = field(default_factory=tuple)
    guard: Optional[str] = None
    require_authentication: bool = True
    title: Optional[str] = None
    allow_client_data: bool = False
    client_data_fields: Sequence[str] = field(default_factory=tuple)
    client_data_schema: Sequence[Dict[str, Any]] = field(default_factory=tuple)


@dataclass
class TemplateDefinition:
    """Runtime representation of a registered PDF template."""

    model: models.Model
    method_name: str
    header_template: str
    content_template: str
    footer_template: str
    url_path: str
    config: Dict[str, Any]
    roles: Sequence[str]
    permissions: Sequence[str]
    guard: Optional[str]
    require_authentication: bool
    title: str
    allow_client_data: bool
    client_data_fields: Sequence[str]
    client_data_schema: Sequence[Dict[str, Any]]


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
    fields: Sequence[str], schema: Sequence[Dict[str, Any]]
) -> Sequence[Dict[str, Any]]:
    """
    Normalize client data schema. When explicit schema is provided, enforce name/type.
    Otherwise derive from field names.
    """

    normalized: Dict[str, Dict[str, Any]] = {}

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
        self._templates: Dict[str, TemplateDefinition] = {}

    def register(
        self, model: models.Model, method_name: str, meta: TemplateMeta
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

    def get(self, url_path: str) -> Optional[TemplateDefinition]:
        """Retrieve a registered template by its URL path."""
        return self._templates.get(url_path)

    def all(self) -> Dict[str, TemplateDefinition]:
        """Expose all templates (primarily for introspection and tests)."""
        return dict(self._templates)


template_registry = TemplateRegistry()


def model_pdf_template(
    *,
    content: str,
    header: Optional[str] = None,
    footer: Optional[str] = None,
    url: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    roles: Optional[Iterable[str]] = None,
    permissions: Optional[Iterable[str]] = None,
    guard: Optional[str] = None,
    require_authentication: bool = True,
    title: Optional[str] = None,
    allow_client_data: bool = False,
    client_data_fields: Optional[Iterable[str]] = None,
    client_data_schema: Optional[Iterable[Dict[str, Any]]] = None,
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


def _render_template(template_path: Optional[str], context: Dict[str, Any]) -> str:
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


def _build_style_block(config: Dict[str, Any]) -> str:
    """
    Convert style configuration into a CSS block usable by WeasyPrint.

    Args:
        config: Style configuration merging defaults and overrides.

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

    return "\n".join(css_chunks)


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

    for attr_name, attr in sender.__dict__.items():
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

    if permission_manager and OperationType:
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

    guard_name = template_def.guard or "retrieve"
    if guard_name:
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


def _extract_client_data(
    request: HttpRequest, template_def: TemplateDefinition
) -> Dict[str, Any]:
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

    data: Dict[str, Any] = {}
    for key in allowed_keys:
        if key in request.GET:
            data[key] = _clean_client_value(request.GET.get(key))

    return data


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
        if not WEASYPRINT_AVAILABLE:
            self._log_template_event(
                request,
                success=False,
                error_message="WeasyPrint is not installed",
                template_path=template_path,
                pk=pk,
            )
            return JsonResponse(
                {
                    "error": "WeasyPrint is not installed",
                    "detail": "Install weasyprint to enable PDF rendering",
                },
                status=500,
            )

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

        context = self._build_context(request, instance, template_def, client_data)

        try:
            pdf_bytes = self._render_pdf(template_def, context)
        except Exception as exc:  # pragma: no cover - defensive logging branch
            logger.exception(
                "Failed to render PDF for %s pk=%s: %s",
                template_def.model.__name__,
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
            return JsonResponse(
                {"error": "Failed to render PDF", "detail": str(exc)}, status=500
            )

        filename = f"{template_def.model._meta.model_name}-{pk}.pdf"
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
        instance: models.Model,
        template_def: TemplateDefinition,
        client_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build template context combining the model instance and method payload.

        Args:
            request: Incoming request.
            instance: Model instance resolved by pk.
            template_def: Template definition holding the method to call.

        Returns:
            Context dictionary for rendering.
        """
        data: Any = {}
        method = getattr(instance, template_def.method_name, None)
        if callable(method):
            try:
                data = method(request)
            except TypeError:
                # Method does not expect the request argument
                data = method()

        return {
            "instance": instance,
            "data": data,
            "request": request,
            "template_config": template_def.config,
            "client_data": client_data or {},
        }

    def _authorize_template_access(
        self,
        request: HttpRequest,
        template_def: TemplateDefinition,
        instance: models.Model,
    ) -> Optional[JsonResponse]:
        """
        Apply RBAC and permission requirements before rendering the PDF.
        """
        user = self._resolve_request_user(request)
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

    def _resolve_request_user(self, request: HttpRequest):
        """
        Retrieve a user from the request session or Authorization header.
        """
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
                    if fallback_user and getattr(
                        fallback_user, "is_authenticated", False
                    ):
                        request.user = fallback_user
                        return fallback_user

        return user

    def _render_pdf(
        self, template_def: TemplateDefinition, context: Dict[str, Any]
    ) -> bytes:
        """
        Render the PDF bytes using WeasyPrint.

        Args:
            template_def: Template definition with paths/config.
            context: Context for rendering.

        Returns:
            PDF as bytes.
        """
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

        header_html = _render_template(template_def.header_template, context)
        content_html = _render_template(template_def.content_template, context)
        footer_html = _render_template(template_def.footer_template, context)

        style_block = _build_style_block(template_def.config)
        html = (
            "<html><head><meta charset='utf-8'><style>"
            f"{style_block}"
            "</style></head><body>"
            f"<div class='pdf-header'>{header_html}</div>"
            f"<div class='pdf-content'>{content_html}</div>"
            f"<div class='pdf-footer'>{footer_html}</div>"
            "</body></html>"
        )

        return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()

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
            details["model"] = template_def.model._meta.label
            details["title"] = template_def.title

        log_audit_event(
            request,
            AuditEventType.DATA_ACCESS,
            success=success,
            error_message=error_message,
            additional_data=details,
        )


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
            f"{prefix}/<path:template_path>/<str:pk>/",
            PdfTemplateView.as_view(),
            name="pdf_template",
        )
    ]


__all__ = [
    "PdfTemplateView",
    "model_pdf_template",
    "template_registry",
    "template_urlpatterns",
    "evaluate_template_access",
]
