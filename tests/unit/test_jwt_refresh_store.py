from unittest.mock import patch

import pytest
from django.test import override_settings

from rail_django.extensions.auth.jwt import (
    RefreshTokenStore,
    _get_refresh_token_store,
    get_refresh_token_store,
)

pytestmark = pytest.mark.unit


@override_settings(JWT_REFRESH_TOKEN_CACHE="missing-test-cache")
def test_refresh_token_fallback_store_persists_between_calls():
    _get_refresh_token_store.cache_clear()
    with patch.object(RefreshTokenStore, "_resolve_cache", return_value=None):
        first = get_refresh_token_store()
        second = get_refresh_token_store()

    first.rotate("family", "token", 60)

    assert first is second
    assert second.ensure_active("family", "token", 60)
    _get_refresh_token_store.cache_clear()
