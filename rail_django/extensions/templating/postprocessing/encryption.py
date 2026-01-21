"""
PDF encryption utilities.

This module provides functions for encrypting PDFs with passwords
and setting document permissions.
"""

import io
from typing import Any

# Optional pypdf import
try:
    from pypdf import PdfReader, PdfWriter

    PYPDF_AVAILABLE = True
except ImportError:
    PdfReader = None
    PdfWriter = None
    PYPDF_AVAILABLE = False


def _resolve_pdf_permissions(permissions: Any) -> Any:
    """
    Convert permissions config to pypdf Permissions object if needed.

    Args:
        permissions: Dict, Permissions object, or None.

    Returns:
        pypdf Permissions object or None.
    """
    if permissions is None:
        return None

    # Already a Permissions object
    if hasattr(permissions, "print_document"):
        return permissions

    if not isinstance(permissions, dict):
        return None

    try:
        from pypdf import Permissions
    except ImportError:
        return None

    # Map common permission keys to Permissions constructor kwargs
    permission_mapping = {
        "print": "print_document",
        "print_document": "print_document",
        "modify": "modify",
        "copy": "extract",
        "extract": "extract",
        "add_annotations": "add_annotations",
        "annotations": "add_annotations",
        "fill_forms": "fill_form_fields",
        "fill_form_fields": "fill_form_fields",
        "extract_for_accessibility": "extract_text_and_graphics",
        "extract_text_and_graphics": "extract_text_and_graphics",
        "assemble": "assemble_document",
        "assemble_document": "assemble_document",
        "print_high_quality": "print_high_quality",
    }

    kwargs = {}
    for key, value in permissions.items():
        mapped_key = permission_mapping.get(str(key).lower())
        if mapped_key:
            kwargs[mapped_key] = bool(value)

    return Permissions(**kwargs) if kwargs else None


def _apply_pdf_encryption(
    pdf_bytes: bytes, encryption: dict[str, Any], *, strict: bool
) -> bytes:
    """
    Apply encryption to a PDF.

    Args:
        pdf_bytes: The original PDF bytes.
        encryption: Encryption configuration dict with keys:
            - user_password or password: Password for opening the document.
            - owner_password: Password for full access (optional).
            - permissions: Dict of permission settings (optional).
        strict: If True, raise errors when pypdf is not available.

    Returns:
        Encrypted PDF bytes.

    Raises:
        RuntimeError: If strict=True and pypdf is not installed.
    """
    if not encryption:
        return pdf_bytes
    if not PYPDF_AVAILABLE or not PdfReader or not PdfWriter:
        if strict:
            raise RuntimeError("pypdf is required for PDF encryption")
        return pdf_bytes

    user_password = encryption.get("user_password") or encryption.get("password") or ""
    owner_password = encryption.get("owner_password")
    permissions = _resolve_pdf_permissions(encryption.get("permissions"))

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    if reader.metadata:
        writer.add_metadata(dict(reader.metadata))

    encrypt_kwargs: dict[str, Any] = {"owner_password": owner_password}
    if permissions is not None:
        encrypt_kwargs["permissions"] = permissions

    writer.encrypt(user_password, **encrypt_kwargs)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
