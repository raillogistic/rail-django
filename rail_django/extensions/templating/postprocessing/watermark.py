"""
PDF watermark utilities.

This module provides functions for applying watermark overlays to PDFs.
"""

import html
import io
from typing import Any, Optional

# Optional pypdf import
try:
    from pypdf import PdfReader, PdfWriter

    PYPDF_AVAILABLE = True
except ImportError:
    PdfReader = None
    PdfWriter = None
    PYPDF_AVAILABLE = False

# Optional WeasyPrint import
try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except ImportError:
    HTML = None
    WEASYPRINT_AVAILABLE = False


def _load_watermark_pdf_bytes(
    watermark: dict[str, Any], *, config: dict[str, Any]
) -> Optional[bytes]:
    """
    Load or generate a watermark PDF.

    Args:
        watermark: Watermark configuration dict with keys:
            - pdf_bytes: Pre-rendered PDF bytes (optional).
            - pdf_path: Path to a PDF file to use as watermark (optional).
            - text: Text to render as a watermark (optional).
        config: Template configuration for page size/orientation.

    Returns:
        Watermark PDF bytes or None if no watermark could be generated.
    """
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
    """
    Apply a watermark overlay to each page of a PDF.

    Args:
        pdf_bytes: The original PDF bytes.
        watermark: Watermark configuration dict with keys:
            - mode: "overlay" to apply as PDF overlay, "css" for CSS-based (default).
            - pdf_bytes, pdf_path, or text: Source for the watermark.
        config: Template configuration.
        strict: If True, raise errors when pypdf is not available.

    Returns:
        PDF bytes with watermark overlay.

    Raises:
        RuntimeError: If strict=True and pypdf is not installed for overlay mode.
    """
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
