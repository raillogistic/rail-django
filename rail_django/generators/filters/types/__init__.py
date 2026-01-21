"""
Filter Types Package.

This package contains all the GraphQL InputObjectType definitions for filtering,
organized by category:

- base_types: String, Int, Float, Boolean, ID, UUID filter inputs
- date_types: Date and DateTime filter inputs
- advanced_types: JSON, Array, and Count filter inputs
- aggregation_types: Aggregation, conditional aggregation, and window function filters
- comparison_types: Subquery, exists, field comparison, date trunc/extract, and full-text search
"""

from .base_types import (
    StringFilterInput,
    IntFilterInput,
    FloatFilterInput,
    BooleanFilterInput,
    IDFilterInput,
    UUIDFilterInput,
)

from .date_types import (
    DateFilterInput,
    DateTimeFilterInput,
)

from .advanced_types import (
    JSONFilterInput,
    ArrayFilterInput,
    CountFilterInput,
)

from .aggregation_types import (
    AggregationFilterInput,
    ConditionalAggregationFilterInput,
    WindowFunctionEnum,
    WindowFilterInput,
)

from .comparison_types import (
    SubqueryFilterInput,
    ExistsFilterInput,
    CompareOperatorEnum,
    FieldCompareFilterInput,
    DateTruncPrecisionEnum,
    DateTruncFilterInput,
    ExtractDateFilterInput,
    FullTextSearchTypeEnum,
    FullTextSearchInput,
)

__all__ = [
    # Base types
    "StringFilterInput",
    "IntFilterInput",
    "FloatFilterInput",
    "BooleanFilterInput",
    "IDFilterInput",
    "UUIDFilterInput",
    # Date types
    "DateFilterInput",
    "DateTimeFilterInput",
    # Advanced types
    "JSONFilterInput",
    "ArrayFilterInput",
    "CountFilterInput",
    # Aggregation types
    "AggregationFilterInput",
    "ConditionalAggregationFilterInput",
    "WindowFunctionEnum",
    "WindowFilterInput",
    # Comparison types
    "SubqueryFilterInput",
    "ExistsFilterInput",
    "CompareOperatorEnum",
    "FieldCompareFilterInput",
    "DateTruncPrecisionEnum",
    "DateTruncFilterInput",
    "ExtractDateFilterInput",
    "FullTextSearchTypeEnum",
    "FullTextSearchInput",
]
