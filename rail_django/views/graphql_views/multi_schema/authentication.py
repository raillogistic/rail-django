"""
Authentication logic for MultiSchemaGraphQLView.
"""

import logging
from typing import Any, Dict, Optional

from django.http import HttpRequest
from ..utils import _get_authenticated_user, _get_effective_schema_settings

logger = logging.getLogger(__name__)


class AuthenticationMixin:
    """Mixin for authentication handling."""

    def _resolve_request_user(self, request: HttpRequest):
        user = _get_authenticated_user(request)
        if user is not None:
            try: request.user = user
            except Exception: pass
        return user

    def _check_authentication(
        self, request: HttpRequest, schema_info: dict[str, Any]
    ) -> bool:
        """Check if the request meets authentication requirements for the schema."""
        schema_settings = _get_effective_schema_settings(schema_info)
        auth_required = schema_settings.get("authentication_required", False)
        superuser_only = bool(
            schema_settings.get("graphiql_superuser_only", False)
            and str(getattr(schema_info, "name", "")).lower() == "graphiql"
        )

        user = self._resolve_request_user(request)
        if user and getattr(user, "is_authenticated", False):
            if superuser_only and not getattr(user, "is_superuser", False):
                return False
            return True

        if not auth_required and not superuser_only:
            return True

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer ") or auth_header.startswith("Token "):
            if self._validate_token(auth_header, schema_settings, request=request):
                user = self._resolve_request_user(request)
                if superuser_only and not (user and getattr(user, "is_superuser", False)):
                    return False
                return True
        return False

    def _validate_token(
        self,
        auth_header: str,
        schema_settings: dict[str, Any],
        request: Optional[HttpRequest] = None,
    ) -> bool:
        """Validate authentication token for schema access."""
        try:
            if auth_header.startswith("Bearer "): token = auth_header.split(" ")[1]
            elif auth_header.startswith("Token "): token = auth_header.split(" ")[1]
            else: return False

            from ....extensions.auth import JWTManager
            payload = JWTManager.verify_token(token, expected_type="access")
            if not payload: return False

            user_id = payload.get("user_id") or payload.get("sub")
            if not user_id: return False

            from django.contrib.auth import get_user_model
            user = get_user_model().objects.filter(id=user_id, is_active=True).first()
            if not user: return False

            if request is not None:
                request.user = user
                request.jwt_payload = payload
            return True
        except Exception as e:
            logger.warning(f"Token validation failed: {str(e)}")
            return False
