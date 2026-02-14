"""
Settings package for Django GraphQL Auto-Generation.
"""

from django.conf import settings as django_settings

from .config import GraphQLAutoConfig
from .filtering_settings import FilteringSettings
from .mutation_settings import MutationGeneratorSettings
from .query_settings import QueryGeneratorSettings
from .schema_settings import SchemaSettings
from .subscription_settings import SubscriptionGeneratorSettings
from .type_settings import TypeGeneratorSettings


DEFAULT_TEST_GRAPHQL_ENDPOINT_PATH = "/graphql-test/"
DEFAULT_TEST_GRAPHQL_ENDPOINT_ENV_KEY = "VITE_TEST_GRAPHQL_ENDPOINT"


def get_test_graphql_endpoint_path() -> str:
    """
    Return the canonical backend test GraphQL endpoint path.

    The frontend uses `VITE_TEST_GRAPHQL_ENDPOINT` as the matching configuration key.
    """
    raw_path = getattr(
        django_settings,
        "RAIL_DJANGO_TEST_GRAPHQL_ENDPOINT_PATH",
        DEFAULT_TEST_GRAPHQL_ENDPOINT_PATH,
    )
    normalized = str(raw_path or DEFAULT_TEST_GRAPHQL_ENDPOINT_PATH).strip()
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    if not normalized.endswith("/"):
        normalized += "/"
    return normalized


__all__ = [
    "TypeGeneratorSettings",
    "QueryGeneratorSettings",
    "FilteringSettings",
    "MutationGeneratorSettings",
    "SubscriptionGeneratorSettings",
    "SchemaSettings",
    "GraphQLAutoConfig",
    "DEFAULT_TEST_GRAPHQL_ENDPOINT_PATH",
    "DEFAULT_TEST_GRAPHQL_ENDPOINT_ENV_KEY",
    "get_test_graphql_endpoint_path",
]
