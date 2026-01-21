"""
Rendering subpackage for PDF templating.

This package provides HTML and PDF rendering capabilities.
"""

from .html import (
    _render_template,
    _build_style_block,
    _css_escape,
    _page_stamp_content,
    _build_page_stamp_css,
    _build_watermark_assets,
    render_template_html,
)

from .pdf import (
    render_pdf_from_html,
    render_pdf,
    PdfBuilder,
)

from .renderers import (
    PdfRenderer,
    WeasyPrintRenderer,
    WkhtmltopdfRenderer,
    register_pdf_renderer,
    get_pdf_renderer,
    WEASYPRINT_AVAILABLE,
)

__all__ = [
    "_render_template",
    "_build_style_block",
    "_css_escape",
    "_page_stamp_content",
    "_build_page_stamp_css",
    "_build_watermark_assets",
    "render_template_html",
    "render_pdf_from_html",
    "render_pdf",
    "PdfBuilder",
    "PdfRenderer",
    "WeasyPrintRenderer",
    "WkhtmltopdfRenderer",
    "register_pdf_renderer",
    "get_pdf_renderer",
    "WEASYPRINT_AVAILABLE",
]
