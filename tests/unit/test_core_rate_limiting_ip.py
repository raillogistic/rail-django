import pytest
from django.test import RequestFactory, override_settings

from rail_django.core.rate_limiting import _get_client_ip


@pytest.mark.unit
@override_settings(RAIL_DJANGO_TRUSTED_PROXIES=["203.0.113.10"])
def test_rate_limiter_ip_uses_forwarded_for_only_from_trusted_proxy():
    request = RequestFactory().get(
        "/graphql/",
        REMOTE_ADDR="203.0.113.10",
        HTTP_X_FORWARDED_FOR="198.51.100.44, 203.0.113.10",
    )
    assert _get_client_ip(request) == "198.51.100.44"


@pytest.mark.unit
@override_settings(RAIL_DJANGO_TRUSTED_PROXIES=["203.0.113.10"])
def test_rate_limiter_ip_ignores_forwarded_for_from_untrusted_proxy():
    request = RequestFactory().get(
        "/graphql/",
        REMOTE_ADDR="198.51.100.77",
        HTTP_X_FORWARDED_FOR="198.51.100.44, 203.0.113.10",
    )
    assert _get_client_ip(request) == "198.51.100.77"
