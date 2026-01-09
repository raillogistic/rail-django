"""
GraphQL Meta utilities for Rail Django GraphQL.

This module provides helper accessors around :class:`rail_django.core.meta.GraphQLMeta`
to keep legacy callers working with the new configuration objects.
"""

from typing import Any, Dict, List, Type

from django.db import models

from ..core.meta import GraphQLMeta, get_model_graphql_meta as _get_model_meta


def get_model_graphql_meta(model: Type[models.Model]) -> GraphQLMeta:
    """
    Return the ``GraphQLMeta`` helper for the provided model.

    Args:
        model: Django model class.
    """

    return _get_model_meta(model)


def get_custom_filters(model: Type[models.Model]) -> Dict[str, Any]:
    """
    Shortcut to fetch custom filter definitions for a model.
    """

    meta = get_model_graphql_meta(model)
    return dict(meta.custom_filters)


def get_quick_filter_fields(model: Type[models.Model]) -> List[str]:
    """
    Shortcut to fetch the quick filter field paths for a model.
    """

    meta = get_model_graphql_meta(model)
    return list(meta.quick_filter_fields)


def get_filter_fields(model: Type[models.Model]) -> Dict[str, List[str]]:
    """
    Shortcut to fetch the filterable field -> lookup mapping.
    """

    meta = get_model_graphql_meta(model)
    return meta.get_filter_fields()
