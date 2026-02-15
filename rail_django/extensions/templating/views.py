"""
PDF template views.

This module provides Django views for serving PDF templates, previews,
and catalog endpoints.
"""

import logging
from typing import Any, Optional

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .config import (
    _merge_dict,
    _patch_pydyf_pdf,
    _templating_async,
    _templating_catalog,
    _templating_expose_errors,
    _templating_preview_enabled,
    _templating_rate_limit,
    _templating_renderer_name,
    _templating_settings,
    _default_header,
    _default_footer,
    PYDYF_VERSION,
    Version,
    InvalidVersion,
)
from .registry import template_registry, TemplateDefinition
from .access import (
    _resolve_request_user,
    _extract_client_data,
    _build_template_context,
    authorize_template_access,
    evaluate_template_access,
)
from .rendering import render_pdf, render_template_html, get_pdf_renderer
from .rendering.pdf import render_pdf_from_html
from .rendering.html import _render_template
from .jobs import (
    _sanitize_filename,
    _cache_settings_for_template,
    _build_pdf_cache_key,
    generate_pdf_async,
)
from ...utils.network import get_rate_limit_identifier

# Re-export job views
from .job_views import PdfTemplateJobStatusView, PdfTemplateJobDownloadView

logger = logging.getLogger(__name__)

# Optional JWT protection (mirrors export endpoints)
try:
    from ..auth.decorators import jwt_required
except ImportError:
    jwt_required = None

# Optional audit logging
try:
    from ...security import security, EventType, Outcome
except ImportError:
    security = None
    EventType = None
    Outcome = None


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
        template_def = template_registry.get(template_path)
        if not template_def:
            self._log_template_event(
                request, success=False, error_message="Template not found",
                template_path=template_path, pk=pk,
            )
            return JsonResponse(
                {"error": "Template not found", "template": template_path}, status=404
            )

        renderer_name = template_def.config.get("renderer") or _templating_renderer_name()
        try:
            get_pdf_renderer(str(renderer_name))
        except Exception as exc:
            self._log_template_event(
                request, success=False, error_message=str(exc),
                template_def=template_def, template_path=template_path, pk=pk,
            )
            return JsonResponse(
                {"error": "PDF renderer unavailable",
                 "detail": str(exc) if _templating_expose_errors() else None},
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
                    request, success=False, error_message="Instance not found",
                    template_def=template_def, template_path=template_path, pk=pk,
                )
                return JsonResponse(
                    {"error": "Instance not found",
                     "model": template_def.model._meta.label, "pk": pk},
                    status=404,
                )
            except (ValidationError, ValueError, TypeError):
                self._log_template_event(
                    request, success=False, error_message="Invalid primary key",
                    template_def=template_def, template_path=template_path, pk=pk,
                )
                return JsonResponse({"error": "Invalid primary key", "pk": pk}, status=400)

        denial = authorize_template_access(request, template_def, instance)
        if denial:
            self._log_template_event(
                request, success=False, error_message="Forbidden",
                template_def=template_def, template_path=template_path, pk=pk,
            )
            return denial

        client_data = _extract_client_data(request, template_def)
        setattr(request, "rail_template_client_data", client_data)
        merge_pks = (
            self._parse_merge_pks(request, pk) if template_def.model else [str(pk)]
        )
        is_multi_render = template_def.model and len(merge_pks) > 1

        if self._parse_async_request(request):
            if is_multi_render:
                return JsonResponse(
                    {"error": "Async PDF jobs do not support multi-row merge."},
                    status=400,
                )
            async_settings = _templating_async()
            if not async_settings.get("enable", False):
                return JsonResponse({"error": "Async PDF jobs are disabled"}, status=400)
            try:
                job_payload = generate_pdf_async(
                    request=request, template_def=template_def, pk=pk,
                    client_data=client_data,
                    base_url=self._resolve_base_url(request, template_def),
                    renderer=renderer_name,
                )
            except Exception as exc:
                return JsonResponse(
                    {"error": "Failed to enqueue PDF job",
                     "detail": str(exc) if _templating_expose_errors() else None},
                    status=500,
                )
            self._log_template_event(
                request, success=True, template_def=template_def,
                template_path=template_path, pk=pk,
            )
            return JsonResponse(job_payload, status=202)

        cache_settings = _cache_settings_for_template(template_def)
        cache_key = None
        if not is_multi_render:
            cache_key = _build_pdf_cache_key(
                template_def,
                pk=pk,
                user=_resolve_request_user(request),
                client_data=client_data,
                cache_settings=cache_settings,
            )
        if cache_key:
            cached_pdf = cache.get(cache_key)
            if cached_pdf:
                response = HttpResponse(cached_pdf, content_type="application/pdf")
                response["Content-Disposition"] = f'inline; filename="{self._resolve_filename(template_def, pk)}"'
                self._log_template_event(
                    request, success=True, template_def=template_def,
                    template_path=template_path, pk=pk,
                )
                return response

        try:
            if is_multi_render:
                contexts: list[dict[str, Any]] = []
                for merge_pk in merge_pks:
                    try:
                        merge_instance = template_def.model.objects.get(pk=merge_pk)
                    except template_def.model.DoesNotExist:
                        return JsonResponse(
                            {
                                "error": "Instance not found",
                                "model": template_def.model._meta.label,
                                "pk": merge_pk,
                            },
                            status=404,
                        )
                    except (ValidationError, ValueError, TypeError):
                        return JsonResponse(
                            {"error": "Invalid primary key", "pk": merge_pk},
                            status=400,
                        )

                    merge_denial = authorize_template_access(
                        request,
                        template_def,
                        merge_instance,
                    )
                    if merge_denial:
                        return merge_denial

                    contexts.append(
                        _build_template_context(
                            request,
                            merge_instance,
                            template_def,
                            client_data,
                            pk=merge_pk,
                        )
                    )

                pdf_bytes = self._render_merged_pdf(
                    template_def,
                    contexts,
                    base_url=self._resolve_base_url(request, template_def),
                    renderer=renderer_name,
                )
            else:
                context = _build_template_context(
                    request,
                    instance,
                    template_def,
                    client_data,
                    pk=pk,
                )
                pdf_bytes = self._render_pdf(
                    template_def,
                    context,
                    base_url=self._resolve_base_url(request, template_def),
                    renderer=renderer_name,
                )
        except Exception as exc:
            model_name = template_def.model.__name__ if template_def.model else template_def.url_path
            logger.exception("Failed to render PDF for %s pk=%s: %s", model_name, pk, exc)
            self._log_template_event(
                request, success=False, error_message=str(exc),
                template_def=template_def, template_path=template_path, pk=pk,
            )
            detail = str(exc) if _templating_expose_errors() else "Failed to render PDF"
            return JsonResponse({"error": "Failed to render PDF", "detail": detail}, status=500)

        if cache_key:
            cache.set(cache_key, pdf_bytes, timeout=int(cache_settings.get("timeout_seconds", 300)))

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{self._resolve_filename(template_def, pk)}"'
        self._log_template_event(
            request, success=True, template_def=template_def,
            template_path=template_path, pk=pk,
        )
        return response

    def _parse_merge_pks(self, request: HttpRequest, fallback_pk: str) -> list[str]:
        raw_values = request.GET.getlist("merge_pks") or request.GET.getlist("mergePks")
        ordered: list[str] = []
        for raw_value in raw_values:
            chunks = str(raw_value or "").split(",")
            for chunk in chunks:
                candidate = str(chunk or "").strip()
                if not candidate or candidate in ordered:
                    continue
                ordered.append(candidate)
        if not ordered:
            return [str(fallback_pk)]
        if str(fallback_pk) not in ordered:
            ordered.insert(0, str(fallback_pk))
        return ordered

    def _parse_async_request(self, request: HttpRequest) -> bool:
        value = request.GET.get("async")
        return value is not None and str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _resolve_base_url(self, request: HttpRequest, template_def: TemplateDefinition) -> str:
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

    def _check_rate_limit(self, request: HttpRequest, template_def: TemplateDefinition) -> Optional[JsonResponse]:
        config = _merge_dict(_templating_rate_limit(), template_def.config.get("rate_limit") or {})
        if not config.get("enable", True):
            return None
        window_seconds = int(config.get("window_seconds", 60))
        max_requests = int(config.get("max_requests", 30))
        identifier = self._get_rate_limit_identifier(request, config)
        cache_key = f"rail:pdf_rl:{identifier}:{template_def.url_path}"
        try:
            current_count = cache.incr(cache_key)
        except ValueError:
            if cache.add(cache_key, 1, timeout=window_seconds):
                return None
            try:
                current_count = cache.incr(cache_key)
            except ValueError:
                cache.set(cache_key, 1, timeout=window_seconds)
                return None
        if current_count > max_requests:
            return JsonResponse({"error": "Rate limit exceeded", "retry_after": window_seconds}, status=429)
        return None

    def _get_rate_limit_identifier(self, request: HttpRequest, rate_limit: dict[str, Any]) -> str:
        trusted_proxies = rate_limit.get("trusted_proxies") or []
        _resolve_request_user(request)
        return get_rate_limit_identifier(request, trusted_proxies)

    def _render_pdf(self, template_def: TemplateDefinition, context: dict[str, Any], *,
                    base_url: Optional[str] = None, renderer: Optional[str] = None) -> bytes:
        renderer_name = str(renderer or template_def.config.get("renderer") or _templating_renderer_name())
        if renderer_name.lower() == "weasyprint":
            if PYDYF_VERSION and Version:
                try:
                    if Version(PYDYF_VERSION) < Version("0.11.0"):
                        raise RuntimeError(f"Incompatible pydyf version {PYDYF_VERSION}; install pydyf>=0.11.0")
                except InvalidVersion:
                    pass
            _patch_pydyf_pdf()
        return render_pdf(
            template_def.content_template, context, config=template_def.config,
            header_template=template_def.header_template,
            footer_template=template_def.footer_template,
            base_url=base_url, renderer=renderer_name,
        )

    def _render_merged_pdf(
        self,
        template_def: TemplateDefinition,
        contexts: list[dict[str, Any]],
        *,
        base_url: Optional[str] = None,
        renderer: Optional[str] = None,
    ) -> bytes:
        if not contexts:
            raise ValueError("At least one context is required for merged rendering.")

        renderer_name = str(
            renderer or template_def.config.get("renderer") or _templating_renderer_name()
        )
        if renderer_name.lower() == "weasyprint":
            if PYDYF_VERSION and Version:
                try:
                    if Version(PYDYF_VERSION) < Version("0.11.0"):
                        raise RuntimeError(
                            f"Incompatible pydyf version {PYDYF_VERSION}; install pydyf>=0.11.0"
                        )
                except InvalidVersion:
                    pass
            _patch_pydyf_pdf()

        first_context = contexts[0]
        header_path = template_def.header_template or _default_header()
        footer_path = template_def.footer_template or _default_footer()
        header_html = _render_template(header_path, first_context)
        footer_html = _render_template(footer_path, first_context)
        rendered_contents: list[str] = []
        for index, context in enumerate(contexts):
            rendered_contents.append(
                _render_template(template_def.content_template, context)
            )
            if index < len(contexts) - 1:
                rendered_contents.append('<div style="page-break-after: always;"></div>')

        html_content = render_template_html(
            header_html=header_html,
            content_html="".join(rendered_contents),
            footer_html=footer_html,
            config=template_def.config,
        )
        return render_pdf_from_html(
            html_content,
            config=template_def.config,
            base_url=base_url,
            renderer=renderer_name,
        )

    def _log_template_event(self, request: HttpRequest, *, success: bool,
                           error_message: Optional[str] = None,
                           template_def: Optional[TemplateDefinition] = None,
                           template_path: Optional[str] = None, pk: Optional[str] = None) -> None:
        if not security or not EventType:
            return

        details = {"template_path": template_path, "pk": pk}
        resource_name = template_path

        if template_def:
            if template_def.model:
                details["model"] = template_def.model._meta.label
                resource_name = template_def.model._meta.label
            details["title"] = template_def.title
            details["source"] = template_def.source

        security.emit(
            EventType.DATA_EXPORT,
            request=request,
            outcome=Outcome.SUCCESS if success else Outcome.FAILURE,
            action="PDF template render",
            resource_type="template",
            resource_name=resource_name,
            resource_id=pk,
            context=details,
            error=error_message
        )


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(jwt_required if jwt_required else (lambda view: view), name="dispatch")
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
        context = _build_template_context(request, instance, template_def, client_data, pk=pk)
        header_html = _render_template(template_def.header_template, context)
        content_html = _render_template(template_def.content_template, context)
        footer_html = _render_template(template_def.footer_template, context)
        html_content = render_template_html(
            header_html=header_html, content_html=content_html,
            footer_html=footer_html, config=template_def.config,
        )
        return HttpResponse(html_content, content_type="text/html")


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(jwt_required if jwt_required else (lambda view: view), name="dispatch")
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
            return JsonResponse({"error": "Authentication required"}, status=401)
        include_config = bool(catalog_settings.get("include_config", False))
        include_permissions = bool(catalog_settings.get("include_permissions", True))
        filter_by_access = bool(catalog_settings.get("filter_by_access", True))
        templates = []
        for url_path, template_def in sorted(template_registry.all().items()):
            access = evaluate_template_access(template_def, user=user, instance=None)
            if filter_by_access and not access.allowed:
                continue
            entry = {
                "url_path": url_path, "title": template_def.title, "source": template_def.source,
                "model": template_def.model._meta.label if template_def.model else None,
                "require_authentication": template_def.require_authentication,
                "allow_client_data": template_def.allow_client_data,
                "client_data_schema": template_def.client_data_schema,
            }
            if include_permissions:
                entry.update({"roles": template_def.roles, "permissions": template_def.permissions, "guard": template_def.guard})
            if include_config:
                entry["config"] = template_def.config
            if not filter_by_access:
                entry["access"] = {"allowed": access.allowed, "reason": access.reason, "status_code": access.status_code}
            templates.append(entry)
        return JsonResponse({"templates": templates})
