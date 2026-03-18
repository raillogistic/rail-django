"""Protected MEDIA_ROOT file delivery for authenticated frontend clients."""

import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse

from .base import BaseAPIView


class ProtectedMediaAPIView(BaseAPIView):
    """Serve MEDIA_ROOT files through the authenticated schema API."""

    auth_required = True
    http_method_names = ["get", "options"]

    @staticmethod
    def _resolve_media_root() -> Path | None:
        configured = str(getattr(settings, "MEDIA_ROOT", "") or "").strip()
        if not configured:
            return None
        try:
            return Path(configured).expanduser().resolve()
        except Exception:
            return None

    @staticmethod
    def _normalize_relative_path(raw_path: str) -> Path | None:
        text = str(raw_path or "").replace("\\", "/").strip().lstrip("/")
        if not text:
            return None

        segments = [
            segment
            for segment in text.split("/")
            if segment and segment not in {".", ".."}
        ]
        if not segments:
            return None
        return Path(*segments)

    def get(self, request, file_path: str) -> HttpResponse:
        media_root = self._resolve_media_root()
        if media_root is None or not media_root.exists() or not media_root.is_dir():
            return self.error_response("Media root not available", status=404)

        relative_path = self._normalize_relative_path(file_path)
        if relative_path is None:
            raise Http404("File not found")

        resolved_file = (media_root / relative_path).resolve()
        try:
            resolved_file.relative_to(media_root)
        except ValueError as exc:
            raise Http404("File not found") from exc

        if not resolved_file.is_file():
            raise Http404("File not found")

        content_type, _ = mimetypes.guess_type(str(resolved_file))
        response = FileResponse(
            open(resolved_file, "rb"),
            content_type=content_type or "application/octet-stream",
        )
        response["Content-Disposition"] = f'inline; filename="{resolved_file.name}"'
        return response
