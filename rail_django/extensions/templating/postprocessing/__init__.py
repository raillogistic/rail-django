"""
PDF postprocessing subpackage.

This package provides PDF postprocessing capabilities including
encryption, watermarking, and digital signatures.
"""

from .encryption import _apply_pdf_encryption, _resolve_pdf_permissions
from .watermark import _apply_pdf_watermark_overlay, _load_watermark_pdf_bytes
from .signature import _apply_pdf_signature

from ..config import _resolve_postprocess_config
from typing import Any, Optional


def _apply_pdf_postprocessing(
    pdf_bytes: bytes,
    *,
    config: Optional[dict[str, Any]] = None,
    postprocess: Optional[dict[str, Any]] = None,
) -> bytes:
    """
    Apply all configured postprocessing operations to a PDF.

    Args:
        pdf_bytes: The original PDF bytes.
        config: Template configuration.
        postprocess: Optional postprocessing overrides.

    Returns:
        Processed PDF bytes.
    """
    config = config or {}
    postprocess_config = _resolve_postprocess_config(config, postprocess)
    if not postprocess_config.get("enable", False):
        return pdf_bytes

    strict = bool(postprocess_config.get("strict", True))
    result = _apply_pdf_watermark_overlay(
        pdf_bytes,
        postprocess_config.get("watermark") or {},
        config=config,
        strict=strict,
    )
    result = _apply_pdf_encryption(
        result, postprocess_config.get("encryption") or {}, strict=strict
    )
    result = _apply_pdf_signature(
        result, postprocess_config.get("signature") or {}, strict=strict
    )
    return result


__all__ = [
    "_apply_pdf_encryption",
    "_resolve_pdf_permissions",
    "_apply_pdf_watermark_overlay",
    "_load_watermark_pdf_bytes",
    "_apply_pdf_signature",
    "_apply_pdf_postprocessing",
]
