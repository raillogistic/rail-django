from django.test import RequestFactory, SimpleTestCase, override_settings

from rail_django.graphql.views.utils import _host_allowed


class TestGraphiQLHostAllowlist(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(ALLOWED_HOSTS=["api.example.com"])
    def test_invalid_host_header_is_not_trusted_for_allowlist_match(self):
        request = self.factory.get(
            "/graphql/graphiql/",
            HTTP_HOST="localhost",
            REMOTE_ADDR="203.0.113.99",
        )

        assert _host_allowed(request, ["localhost"]) is False

    @override_settings(
        ALLOWED_HOSTS=["example.com"],
        RAIL_DJANGO_TRUSTED_PROXIES=[],
    )
    def test_untrusted_proxy_does_not_use_x_forwarded_for(self):
        request = self.factory.get(
            "/graphql/graphiql/",
            HTTP_HOST="example.com",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_FORWARDED_FOR="127.0.0.1",
        )

        assert _host_allowed(request, ["127.0.0.1"]) is False

    @override_settings(
        ALLOWED_HOSTS=["example.com"],
        RAIL_DJANGO_TRUSTED_PROXIES=["203.0.113.10"],
    )
    def test_trusted_proxy_uses_x_forwarded_for(self):
        request = self.factory.get(
            "/graphql/graphiql/",
            HTTP_HOST="example.com",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_FORWARDED_FOR="127.0.0.1",
        )

        assert _host_allowed(request, ["127.0.0.1"]) is True
