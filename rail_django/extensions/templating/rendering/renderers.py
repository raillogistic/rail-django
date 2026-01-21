"""
PDF renderer implementations.

This module provides the PdfRenderer base class and concrete implementations
for WeasyPrint and wkhtmltopdf renderers.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from ..config import _templating_renderer_name

# Optional WeasyPrint import
try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except ImportError:
    HTML = None
    WEASYPRINT_AVAILABLE = False


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
    """PDF renderer using WeasyPrint."""

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
    """PDF renderer using wkhtmltopdf command-line tool."""

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


# ---------------------------------------------------------------------------
# Renderer registry
# ---------------------------------------------------------------------------

_RENDERER_REGISTRY: dict[str, PdfRenderer] = {}


def register_pdf_renderer(name: str, renderer: PdfRenderer) -> None:
    """
    Register a PDF renderer.

    Args:
        name: Name to register the renderer under.
        renderer: PdfRenderer instance.
    """
    _RENDERER_REGISTRY[name] = renderer


def get_pdf_renderer(name: Optional[str] = None) -> PdfRenderer:
    """
    Get a PDF renderer by name.

    Args:
        name: Name of the renderer. Uses default from settings when None.

    Returns:
        PdfRenderer instance.

    Raises:
        RuntimeError: If the requested renderer is not available.
    """
    renderer_name = (name or _templating_renderer_name()).lower()
    renderer = _RENDERER_REGISTRY.get(renderer_name)
    if renderer:
        return renderer
    if "weasyprint" in _RENDERER_REGISTRY:
        return _RENDERER_REGISTRY["weasyprint"]
    raise RuntimeError(f"PDF renderer '{renderer_name}' is not available")


# Register default renderers
if WEASYPRINT_AVAILABLE:
    register_pdf_renderer("weasyprint", WeasyPrintRenderer())
register_pdf_renderer("wkhtmltopdf", WkhtmltopdfRenderer())
