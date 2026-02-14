from django.test import RequestFactory, SimpleTestCase, override_settings

from rail_django.graphql.views.utils import (
    _is_production_environment,
    _is_test_graphql_endpoint_enabled,
    _is_test_graphql_endpoint_request,
)


class TestGraphQLTestEndpointPolicy(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(DEBUG=False, ENVIRONMENT=None)
    def test_defaults_to_production_when_debug_is_false(self):
        assert _is_production_environment() is True
        assert _is_test_graphql_endpoint_enabled() is False

    @override_settings(DEBUG=True, ENVIRONMENT=None)
    def test_debug_defaults_to_non_production(self):
        assert _is_production_environment() is False
        assert _is_test_graphql_endpoint_enabled() is True

    @override_settings(ENVIRONMENT="production")
    def test_explicit_production_environment_blocks_test_endpoint(self):
        assert _is_production_environment() is True
        assert _is_test_graphql_endpoint_enabled() is False

    @override_settings(ENVIRONMENT="development")
    def test_non_production_environment_enables_test_endpoint(self):
        assert _is_production_environment() is False
        assert _is_test_graphql_endpoint_enabled() is True

    @override_settings(
        ENVIRONMENT="production",
        RAIL_DJANGO_ENABLE_TEST_GRAPHQL_ENDPOINT=True,
    )
    def test_explicit_enable_overrides_environment_default(self):
        assert _is_production_environment() is True
        assert _is_test_graphql_endpoint_enabled() is True

    @override_settings(
        ENVIRONMENT="development",
        RAIL_DJANGO_ENABLE_TEST_GRAPHQL_ENDPOINT=False,
    )
    def test_explicit_disable_overrides_environment_default(self):
        assert _is_production_environment() is False
        assert _is_test_graphql_endpoint_enabled() is False

    def test_test_endpoint_request_detection_with_default_path(self):
        request = self.factory.get("/graphql-test/")
        assert _is_test_graphql_endpoint_request(request) is True

        schema_request = self.factory.get("/graphql-test/gql/")
        assert _is_test_graphql_endpoint_request(schema_request) is True

        standard_graphql_request = self.factory.get("/graphql/")
        assert _is_test_graphql_endpoint_request(standard_graphql_request) is False

    @override_settings(RAIL_DJANGO_TEST_GRAPHQL_ENDPOINT_PATH="integration/graphql")
    def test_test_endpoint_request_detection_with_custom_path(self):
        request = self.factory.get("/integration/graphql/")
        assert _is_test_graphql_endpoint_request(request) is True

        other_request = self.factory.get("/graphql-test/")
        assert _is_test_graphql_endpoint_request(other_request) is False
