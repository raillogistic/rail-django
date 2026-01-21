"""
PDF digital signature utilities.

This module provides functions for applying digital signatures to PDFs.
"""

import io
from typing import Any


def _apply_pdf_signature(
    pdf_bytes: bytes, signature: dict[str, Any], *, strict: bool
) -> bytes:
    """
    Apply a digital signature to a PDF.

    Args:
        pdf_bytes: The original PDF bytes.
        signature: Signature configuration dict with keys:
            - handler: Custom signing handler callable (optional).
            - pfx_path: Path to PKCS#12 certificate file.
            - pfx_password: Password for the certificate (optional).
            - field_name: Name for the signature field (default: "Signature1").
            - reason: Reason for signing (optional).
            - location: Location of signing (optional).
            - contact_info: Contact information (optional).
        strict: If True, raise errors when pyhanko is not available.

    Returns:
        Signed PDF bytes.

    Raises:
        RuntimeError: If strict=True and required dependencies are missing.
    """
    if not signature:
        return pdf_bytes
    handler = signature.get("handler")
    if callable(handler):
        return handler(pdf_bytes)

    pfx_path = signature.get("pfx_path")
    if not pfx_path:
        if strict:
            raise RuntimeError("Signature configuration requires a handler or pfx_path")
        return pdf_bytes
    try:
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers
    except ImportError:
        if strict:
            raise RuntimeError("pyhanko is required for PDF signing")
        return pdf_bytes

    passphrase = signature.get("pfx_password")
    if isinstance(passphrase, str):
        passphrase = passphrase.encode("utf-8")
    signer = signers.SimpleSigner.load_pkcs12(pfx_path, passphrase=passphrase)
    field_name = signature.get("field_name", "Signature1")
    reason = signature.get("reason")
    location = signature.get("location")
    contact_info = signature.get("contact_info")
    signature_meta = signers.PdfSignatureMetadata(
        field_name=field_name,
        reason=reason,
        location=location,
        contact_info=contact_info,
    )
    output = io.BytesIO()
    signers.sign_pdf(
        IncrementalPdfFileWriter(io.BytesIO(pdf_bytes)),
        signature_meta,
        signer=signer,
        output=output,
    )
    return output.getvalue()
