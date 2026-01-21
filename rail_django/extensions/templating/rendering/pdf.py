"""
PDF rendering functions and PdfBuilder class.

This module provides the core PDF rendering functionality including
the render_pdf and render_pdf_from_html functions, as well as
the PdfBuilder class for builder-style PDF composition.
"""

from typing import Any, Callable, Optional

from django.conf import settings

from ..config import (
    _default_footer,
    _default_header,
    _default_template_config,
    _resolve_url_fetcher,
    _patch_pydyf_pdf,
    _templating_renderer_name,
    PYDYF_VERSION,
    Version,
    InvalidVersion,
)
from ..postprocessing import _apply_pdf_postprocessing
from .html import _render_template, render_template_html
from .renderers import get_pdf_renderer


def render_pdf_from_html(
    html_content: str,
    *,
    config: Optional[dict[str, Any]] = None,
    base_url: Optional[str] = None,
    url_fetcher: Optional[Callable] = None,
    renderer: Optional[str] = None,
    postprocess: Optional[dict[str, Any]] = None,
) -> bytes:
    """
    Render a PDF from raw HTML content.

    Args:
        html_content: Complete HTML document string.
        config: Style configuration.
        base_url: Base URL for resolving relative URLs in the HTML.
        url_fetcher: Custom URL fetcher callable.
        renderer: Name of the renderer to use.
        postprocess: Optional postprocessing configuration.

    Returns:
        PDF bytes.
    """
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
    """
    Render a PDF from Django templates.

    Args:
        template: Path to the content template.
        context: Context dictionary for template rendering.
        config: Style configuration.
        header_template: Path to header template. Uses default when None.
        footer_template: Path to footer template. Uses default when None.
        base_url: Base URL for resolving relative URLs.
        url_fetcher: Custom URL fetcher callable.
        renderer: Name of the renderer to use.
        postprocess: Optional postprocessing configuration.

    Returns:
        PDF bytes.
    """
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
