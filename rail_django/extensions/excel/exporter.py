"""
Main Excel export logic.

This module provides the Excel template registry, decorators, and data
extraction helpers for the Excel export functionality.
"""

import inspect
import logging
from typing import Any, Callable, Dict, Iterable, Optional, Type

from django.db import models
from django.db.models.signals import class_prepared
from django.http import HttpRequest

from .access import (
    _resolve_request_user,
    authorize_excel_template_access,
    evaluate_excel_template_access,
)
from .config import (
    ExcelData,
    ExcelTemplateDefinition,
    ExcelTemplateMeta,
    _default_excel_config,
    _derive_excel_template_title,
    _derive_function_title,
    _url_prefix,
)

logger = logging.getLogger(__name__)


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


def _extract_client_data(
    request: HttpRequest, template_def: ExcelTemplateDefinition
) -> Dict[str, Any]:
    """
    Extract whitelisted client-provided values from the request.

    Args:
        request: The HTTP request.
        template_def: The template definition with client_data configuration.

    Returns:
        Dictionary of allowed client data values.
    """
    if not template_def.allow_client_data:
        return {}

    allowed_keys = {str(k) for k in (template_def.client_data_fields or [])}
    if not allowed_keys:
        data: Dict[str, Any] = {}
        for key in request.GET.keys():
            data[key] = _clean_client_value(request.GET.get(key))
        return data

    data = {}
    for key in allowed_keys:
        if key in request.GET:
            data[key] = _clean_client_value(request.GET.get(key))

    return data


class ExcelTemplateRegistry:
    """Keeps track of all registered Excel templates exposed by models."""

    def __init__(self) -> None:
        self._templates: Dict[str, ExcelTemplateDefinition] = {}

    def register(
        self, model: Type[models.Model], method_name: str, meta: ExcelTemplateMeta
    ) -> None:
        """
        Register an Excel template for a model method.

        Args:
            model: Django model class owning the method.
            method_name: Name of the decorated method.
            meta: Raw decorator metadata.
        """
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        url_path = meta.url_path or f"{app_label}/{model_name}/{method_name}"

        merged_config = {**_default_excel_config(), **(meta.config or {})}
        title = meta.title or _derive_excel_template_title(model, method_name)

        definition = ExcelTemplateDefinition(
            model=model,
            method_name=method_name,
            handler=None,
            source="model",
            url_path=url_path,
            config=merged_config,
            roles=tuple(meta.roles or ()),
            permissions=tuple(meta.permissions or ()),
            guard=meta.guard,
            require_authentication=meta.require_authentication,
            title=title,
            allow_client_data=bool(meta.allow_client_data),
            client_data_fields=tuple(meta.client_data_fields or ()),
        )

        self._templates[url_path] = definition
        logger.info(
            "Registered Excel template for %s.%s at /api/%s/%s/<pk>/",
            model.__name__,
            method_name,
            _url_prefix(),
            url_path,
        )

    def register_function(self, func: Callable, meta: ExcelTemplateMeta) -> None:
        """
        Register an Excel template for a standalone function.

        Args:
            func: Callable that returns data for the Excel file.
            meta: Raw decorator metadata.
        """
        module_label = str(getattr(func, "__module__", "")).split(".")[-1] or "excel"
        url_path = meta.url_path or f"{module_label}/{func.__name__}"

        merged_config = {**_default_excel_config(), **(meta.config or {})}
        title = meta.title or _derive_function_title(func)

        definition = ExcelTemplateDefinition(
            model=None,
            method_name=None,
            handler=func,
            source="function",
            url_path=url_path,
            config=merged_config,
            roles=tuple(meta.roles or ()),
            permissions=tuple(meta.permissions or ()),
            guard=meta.guard,
            require_authentication=meta.require_authentication,
            title=title,
            allow_client_data=bool(meta.allow_client_data),
            client_data_fields=tuple(meta.client_data_fields or ()),
        )

        self._templates[url_path] = definition
        logger.info(
            "Registered function Excel template for %s at /api/%s/%s/<pk>/",
            func.__name__,
            _url_prefix(),
            url_path,
        )

    def get(self, url_path: str) -> Optional[ExcelTemplateDefinition]:
        """Retrieve a registered template by its URL path."""
        return self._templates.get(url_path)

    def all(self) -> Dict[str, ExcelTemplateDefinition]:
        """Expose all templates (primarily for introspection and tests)."""
        return dict(self._templates)


excel_template_registry = ExcelTemplateRegistry()


def model_excel_template(
    *,
    url: Optional[str] = None,
    title: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    roles: Optional[Iterable[str]] = None,
    permissions: Optional[Iterable[str]] = None,
    guard: Optional[str] = None,
    require_authentication: bool = True,
    allow_client_data: bool = False,
    client_data_fields: Optional[Iterable[str]] = None,
) -> Callable:
    """
    Decorator to expose a model method as an Excel endpoint.

    The decorated function should return data in one of these formats:
    - Single sheet: list[list[Any]] where first row is headers
    - Multi-sheet: dict[str, list[list[Any]]] where keys are sheet names

    Args:
        url: Relative URL for the Excel endpoint.
        title: Optional human-readable label.
        config: Optional style overrides.
        roles: Optional RBAC role names required.
        permissions: Optional Django permission strings required.
        guard: Optional GraphQL guard name.
        require_authentication: Whether authentication is mandatory.
        allow_client_data: Whether to extract query parameters.
        client_data_fields: Optional allowed query parameter names.

    Returns:
        The original function with attached metadata.
    """

    def decorator(func: Callable) -> Callable:
        func._excel_template_meta = ExcelTemplateMeta(
            url_path=url,
            config=config or {},
            roles=tuple(roles or ()),
            permissions=tuple(permissions or ()),
            guard=guard,
            require_authentication=require_authentication,
            title=title,
            allow_client_data=allow_client_data,
            client_data_fields=tuple(client_data_fields or ()),
        )
        return func

    return decorator


def excel_template(
    *,
    url: Optional[str] = None,
    title: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    roles: Optional[Iterable[str]] = None,
    permissions: Optional[Iterable[str]] = None,
    guard: Optional[str] = None,
    require_authentication: bool = True,
    allow_client_data: bool = False,
    client_data_fields: Optional[Iterable[str]] = None,
) -> Callable:
    """
    Decorator to expose a standalone function as an Excel endpoint.

    Args:
        url: Relative URL for the Excel endpoint.
        title: Optional human-readable label.
        config: Optional style overrides.
        roles: Optional RBAC role names required.
        permissions: Optional Django permission strings required.
        guard: Optional GraphQL guard name.
        require_authentication: Whether authentication is mandatory.
        allow_client_data: Whether to extract query parameters.
        client_data_fields: Optional allowed query parameter names.

    Returns:
        The decorated function.
    """

    def decorator(func: Callable) -> Callable:
        meta = ExcelTemplateMeta(
            url_path=url,
            config=config or {},
            roles=tuple(roles or ()),
            permissions=tuple(permissions or ()),
            guard=guard,
            require_authentication=require_authentication,
            title=title,
            allow_client_data=allow_client_data,
            client_data_fields=tuple(client_data_fields or ()),
        )
        func._excel_template_meta = meta
        excel_template_registry.register_function(func, meta)
        return func

    return decorator


def _register_model_excel_templates(sender: Any, **kwargs: Any) -> None:
    """Signal handler to register decorated methods once models are ready."""
    if not hasattr(sender, "_meta"):
        return
    if sender._meta.abstract:
        return

    for attr_name, attr in inspect.getmembers(sender, predicate=callable):
        meta: Optional[ExcelTemplateMeta] = getattr(attr, "_excel_template_meta", None)
        if not meta:
            continue

        excel_template_registry.register(sender, attr_name, meta)


class_prepared.connect(
    _register_model_excel_templates, dispatch_uid="excel_template_registration"
)


def _register_existing_models_if_ready() -> None:
    """Register templates for models that were loaded before the module import."""
    try:
        from django.apps import apps

        if not apps.ready:
            return

        for model in apps.get_models():
            _register_model_excel_templates(model)
    except Exception as exc:  # pragma: no cover
        logger.debug("Skipping eager Excel template registration: %s", exc)


_register_existing_models_if_ready()


def _call_model_method(method: Optional[Callable], request: HttpRequest) -> Any:
    """Call a model method with optional request parameter."""
    if not callable(method):
        return []
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
    has_var_keyword = any(param.kind == param.VAR_KEYWORD for param in params.values())
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
    """Call a standalone function handler with request and pk parameters."""
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
    args: list = []
    kwargs: Dict[str, Any] = {}

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


def _get_excel_data(
    request: HttpRequest,
    instance: Optional[models.Model],
    template_def: ExcelTemplateDefinition,
    pk: Optional[str] = None,
) -> ExcelData:
    """Get data from the decorated method or function."""
    if template_def.source == "model":
        method = getattr(instance, template_def.method_name or "", None)
        return _call_model_method(method, request)
    elif template_def.handler:
        return _call_function_handler(template_def.handler, request, pk)
    return []


__all__ = [
    # Registry
    "ExcelTemplateRegistry",
    "excel_template_registry",
    # Decorators
    "model_excel_template",
    "excel_template",
    # Access control (re-exported from access.py)
    "_resolve_request_user",
    "evaluate_excel_template_access",
    "authorize_excel_template_access",
    # Client data
    "_clean_client_value",
    "_extract_client_data",
    # Data extraction
    "_call_model_method",
    "_call_function_handler",
    "_get_excel_data",
]
