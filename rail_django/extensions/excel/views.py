"""
Excel export Django views.

This module provides the Django views for serving Excel exports,
including the main template view and catalog.
"""

import ipaddress
import logging
from typing import Any, Dict, Iterable, Optional

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .builder import OPENPYXL_AVAILABLE, render_excel
from .config import (
    ExcelTemplateDefinition,
    _excel_async,
    _excel_catalog,
    _excel_expose_errors,
    _excel_rate_limit,
    _merge_dict,
)
from .jobs import (
    _build_excel_cache_key,
    _cache_settings_for_template,
    _sanitize_filename,
    generate_excel_async,
)

# Re-export job views for backward compatibility
from .job_views import ExcelTemplateJobDownloadView, ExcelTemplateJobStatusView

# Optional imports
try:
    from ..auth_decorators import jwt_required
except ImportError:
    jwt_required = None

try:
    from ..audit import AuditEventType, log_audit_event
except ImportError:
    AuditEventType = None
    log_audit_event = None

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(
    jwt_required if jwt_required else (lambda view: view), name="dispatch"
)
class ExcelTemplateView(View):
    """Serve model Excel files rendered with openpyxl."""

    http_method_names = ["get"]

    def get(
        self,
        request: HttpRequest,
        template_path: str,
        *args: Any,
        **kwargs: Any,
    ) -> HttpResponse:
        """
        Generate an Excel file for a given model instance.

        Args:
            request: Incoming Django request.
            template_path: Relative template path registered for the model.

        Query Parameters:
            pk: Primary key of the model instance (optional for function templates).

        Returns:
            Excel response or JSON error when unavailable.
        """
        from .access import _resolve_request_user
        from .exporter import (
            _extract_client_data,
            _get_excel_data,
            authorize_excel_template_access,
            excel_template_registry,
        )

        pk = request.GET.get("pk")

        template_def = excel_template_registry.get(template_path)
        if not template_def:
            self._log_template_event(
                request, success=False, error_message="Template not found",
                template_path=template_path, pk=pk,
            )
            return JsonResponse(
                {"error": "Template not found", "template": template_path}, status=404
            )

        if not OPENPYXL_AVAILABLE:
            self._log_template_event(
                request, success=False, error_message="openpyxl not available",
                template_def=template_def, template_path=template_path, pk=pk,
            )
            return JsonResponse(
                {
                    "error": "Excel export unavailable",
                    "detail": "openpyxl is not installed" if _excel_expose_errors() else None,
                },
                status=500,
            )

        rate_limit_response = self._check_rate_limit(request, template_def)
        if rate_limit_response:
            return rate_limit_response

        instance: Optional[models.Model] = None
        if template_def.model:
            if not pk:
                return JsonResponse(
                    {"error": "Missing required parameter 'pk'"}, status=400
                )
            try:
                instance = template_def.model.objects.get(pk=pk)
            except template_def.model.DoesNotExist:
                self._log_template_event(
                    request, success=False, error_message="Instance not found",
                    template_def=template_def, template_path=template_path, pk=pk,
                )
                return JsonResponse(
                    {"error": "Instance not found", "model": template_def.model._meta.label, "pk": pk},
                    status=404,
                )
            except (ValidationError, ValueError, TypeError):
                self._log_template_event(
                    request, success=False, error_message="Invalid primary key",
                    template_def=template_def, template_path=template_path, pk=pk,
                )
                return JsonResponse({"error": "Invalid primary key", "pk": pk}, status=400)

        denial = authorize_excel_template_access(request, template_def, instance)
        if denial:
            self._log_template_event(
                request, success=False, error_message="Forbidden",
                template_def=template_def, template_path=template_path, pk=pk,
            )
            return denial

        client_data = _extract_client_data(request, template_def)
        setattr(request, "rail_excel_client_data", client_data)

        if self._parse_async_request(request):
            async_settings = _excel_async()
            if not async_settings.get("enable", False):
                return JsonResponse({"error": "Async Excel jobs are disabled"}, status=400)
            try:
                job_payload = generate_excel_async(request=request, template_def=template_def, pk=pk)
            except Exception as exc:
                return JsonResponse(
                    {"error": "Failed to enqueue Excel job", "detail": str(exc) if _excel_expose_errors() else None},
                    status=500,
                )
            self._log_template_event(
                request, success=True, template_def=template_def, template_path=template_path, pk=pk,
            )
            return JsonResponse(job_payload, status=202)

        cache_settings = _cache_settings_for_template(template_def)
        cache_key = _build_excel_cache_key(
            template_def, pk=pk, user=_resolve_request_user(request), cache_settings=cache_settings,
        )
        if cache_key:
            cached_excel = cache.get(cache_key)
            if cached_excel:
                response = HttpResponse(
                    cached_excel, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                response["Content-Disposition"] = f'attachment; filename="{self._resolve_filename(template_def, pk)}"'
                self._log_template_event(
                    request, success=True, template_def=template_def, template_path=template_path, pk=pk,
                )
                return response

        try:
            data = _get_excel_data(request, instance, template_def, pk)
            excel_bytes = render_excel(data, config=template_def.config)
        except Exception as exc:  # pragma: no cover
            model_name = template_def.model.__name__ if template_def.model else template_def.url_path
            logger.exception("Failed to render Excel for %s pk=%s: %s", model_name, pk, exc)
            self._log_template_event(
                request, success=False, error_message=str(exc),
                template_def=template_def, template_path=template_path, pk=pk,
            )
            detail = str(exc) if _excel_expose_errors() else "Failed to render Excel"
            return JsonResponse({"error": "Failed to render Excel", "detail": detail}, status=500)

        if cache_key:
            cache.set(cache_key, excel_bytes, timeout=int(cache_settings.get("timeout_seconds", 300)))

        filename = self._resolve_filename(template_def, pk)
        response = HttpResponse(
            excel_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        self._log_template_event(
            request, success=True, template_def=template_def, template_path=template_path, pk=pk,
        )
        return response

    def _parse_async_request(self, request: HttpRequest) -> bool:
        """Check if the request wants async processing."""
        value = request.GET.get("async")
        if value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _resolve_filename(self, template_def: ExcelTemplateDefinition, pk: Optional[str]) -> str:
        """Generate a filename for the Excel download."""
        if template_def.model:
            base_name = f"{template_def.model._meta.model_name}-{pk}"
        else:
            base_name = f"{template_def.url_path.replace('/', '-')}-{pk}"
        return f"{_sanitize_filename(base_name)}.xlsx"

    def _get_rate_limit_identifier(self, request: HttpRequest, rate_limit: Dict[str, Any]) -> str:
        """Get the rate limit identifier for a request."""
        from .access import _resolve_request_user
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
        """Check if a remote address is a trusted proxy."""
        if not remote_addr:
            return False
        for proxy in trusted_proxies:
            proxy = str(proxy).strip()
            if not proxy:
                continue
            if "/" in proxy:
                try:
                    if ipaddress.ip_address(remote_addr) in ipaddress.ip_network(proxy, strict=False):
                        return True
                except ValueError:
                    continue
            if remote_addr == proxy:
                return True
        return False

    def _check_rate_limit(self, request: HttpRequest, template_def: ExcelTemplateDefinition) -> Optional[JsonResponse]:
        """Check rate limits for the request."""
        config = _excel_rate_limit()
        overrides = template_def.config.get("rate_limit") or {}
        config = _merge_dict(config, overrides)
        if not config.get("enable", True):
            return None
        window_seconds = int(config.get("window_seconds", 60))
        max_requests = int(config.get("max_requests", 30))
        identifier = self._get_rate_limit_identifier(request, config)
        cache_key = f"rail:excel_rl:{identifier}:{template_def.url_path}"
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

    def _log_template_event(
        self, request: HttpRequest, *, success: bool, error_message: Optional[str] = None,
        template_def: Optional[ExcelTemplateDefinition] = None,
        template_path: Optional[str] = None, pk: Optional[str] = None,
    ) -> None:
        """Log an audit event for template rendering."""
        if not log_audit_event or not AuditEventType:
            return
        details: Dict[str, Any] = {"action": "excel_template_render", "template_path": template_path, "pk": pk}
        if template_def:
            if template_def.model:
                details["model"] = template_def.model._meta.label
            details["title"] = template_def.title
            details["source"] = template_def.source
        log_audit_event(request, AuditEventType.DATA_ACCESS, success=success, error_message=error_message, additional_data=details)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(jwt_required if jwt_required else (lambda view: view), name="dispatch")
class ExcelTemplateCatalogView(View):
    """Expose Excel template catalog metadata for UI-driven workflows."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest) -> JsonResponse:
        """Return the catalog of available Excel templates."""
        from .access import _resolve_request_user
        from .exporter import evaluate_excel_template_access, excel_template_registry

        catalog_settings = _excel_catalog()
        if not catalog_settings.get("enable", True):
            raise Http404("Catalog disabled")

        user = _resolve_request_user(request)
        if catalog_settings.get("require_authentication", True) and not (user and getattr(user, "is_authenticated", False)):
            return JsonResponse({"error": "Authentication required"}, status=401)

        include_config = bool(catalog_settings.get("include_config", False))
        include_permissions = bool(catalog_settings.get("include_permissions", True))
        filter_by_access = bool(catalog_settings.get("filter_by_access", True))

        templates = []
        for url_path, template_def in sorted(excel_template_registry.all().items()):
            access = evaluate_excel_template_access(template_def, user=user, instance=None)
            if filter_by_access and not access.allowed:
                continue
            entry: Dict[str, Any] = {
                "url_path": url_path, "title": template_def.title, "source": template_def.source,
                "model": template_def.model._meta.label if template_def.model else None,
                "require_authentication": template_def.require_authentication,
            }
            if include_permissions:
                entry.update({"roles": template_def.roles, "permissions": template_def.permissions, "guard": template_def.guard})
            if include_config:
                entry["config"] = template_def.config
            if not filter_by_access:
                entry["access"] = {"allowed": access.allowed, "reason": access.reason, "status_code": access.status_code}
            templates.append(entry)

        return JsonResponse({"templates": templates})


__all__ = [
    "ExcelTemplateView",
    "ExcelTemplateCatalogView",
    "ExcelTemplateJobStatusView",
    "ExcelTemplateJobDownloadView",
]
