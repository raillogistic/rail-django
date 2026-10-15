from types import SimpleNamespace

import pytest
from graphql import GraphQLError

from rail_django.generators.filters.applicator.field_applicator import (
    FieldFilterApplicatorMixin,
)

pytestmark = pytest.mark.unit


class _Candidates(list):
    def count(self):
        return len(self)


def test_property_filter_rejects_unbounded_candidate_sets():
    applicator = FieldFilterApplicatorMixin()
    applicator.filtering_settings = SimpleNamespace(max_property_filtering_results=1)

    with pytest.raises(GraphQLError, match="limited to 1 candidate rows"):
        applicator._build_property_q(
            "computed",
            {"eq": "value"},
            property_context={"queryset": _Candidates([object(), object()])},
        )
