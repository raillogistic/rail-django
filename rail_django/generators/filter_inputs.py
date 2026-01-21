"""
Nested Filter Input Types for GraphQL (Prisma/Hasura Style)

This module is a backward-compatibility facade. The implementation has been
refactored into the `rail_django.generators.filters` package.

DEPRECATION NOTICE:
    Importing from `rail_django.generators.filter_inputs` is deprecated.
    Please update your imports to use `rail_django.generators.filters` instead.

Example migration:
    # Old (deprecated):
    from rail_django.generators.filter_inputs import (
        StringFilterInput,
        NestedFilterInputGenerator,
        FilterSecurityError,
    )

    # New (recommended):
    from rail_django.generators.filters import (
        StringFilterInput,
        NestedFilterInputGenerator,
        FilterSecurityError,
    )
"""

import warnings

# Issue deprecation warning on import
warnings.warn(
    "Importing from 'rail_django.generators.filter_inputs' is deprecated. "
    "Use 'rail_django.generators.filters' instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from the new package for backward compatibility
from .filters import (
    # Generator
    NestedFilterInputGenerator,
    generate_where_input_for_model,
    # Applicator
    NestedFilterApplicator,
    apply_where_filter,
    # Generator utilities
    get_filter_input_for_field,
    is_historical_model,
    generate_computed_filters,
    generate_array_field_filters,
    generate_date_trunc_filters,
    generate_date_extract_filters,
    generate_historical_filters,
    get_advanced_filter_types,
    DEFAULT_MAX_NESTED_DEPTH,
    MAX_ALLOWED_NESTED_DEPTH,
    DEFAULT_CACHE_MAX_SIZE,
    FIELD_TYPE_TO_FILTER_INPUT,
    # Security
    FilterSecurityError,
    validate_regex_pattern,
    validate_filter_depth,
    count_filter_clauses,
    validate_filter_complexity,
    get_nested_filter_applicator,
    get_nested_filter_generator,
    clear_filter_caches,
    DEFAULT_MAX_REGEX_LENGTH,
    DEFAULT_MAX_FILTER_DEPTH,
    DEFAULT_MAX_FILTER_CLAUSES,
    _filter_generator_registry,
    _filter_applicator_registry,
    # Base types
    StringFilterInput,
    IntFilterInput,
    FloatFilterInput,
    BooleanFilterInput,
    IDFilterInput,
    UUIDFilterInput,
    # Date types
    DateFilterInput,
    DateTimeFilterInput,
    # Advanced types
    JSONFilterInput,
    ArrayFilterInput,
    CountFilterInput,
    # Aggregation types
    AggregationFilterInput,
    ConditionalAggregationFilterInput,
    WindowFunctionEnum,
    WindowFilterInput,
    # Comparison types
    SubqueryFilterInput,
    ExistsFilterInput,
    FieldCompareFilterInput,
    CompareOperatorEnum,
    DateTruncPrecisionEnum,
    DateTruncFilterInput,
    ExtractDateFilterInput,
    FullTextSearchTypeEnum,
    FullTextSearchInput,
    # Mixins
    QuickFilterMixin,
    IncludeFilterMixin,
    HistoricalModelMixin,
    GraphQLMetaIntegrationMixin,
    SchemaSettingsMixin,
    # Analysis
    PerformanceAnalyzer,
    FilterOperation,
    GroupedFieldFilter,
    FilterMetadataGenerator,
    # Advanced generators
    AdvancedFilterGenerator,
    EnhancedFilterGenerator,
)

__all__ = [
    # Generator
    "NestedFilterInputGenerator",
    "generate_where_input_for_model",
    # Applicator
    "NestedFilterApplicator",
    "apply_where_filter",
    # Generator utilities
    "get_filter_input_for_field",
    "is_historical_model",
    "generate_computed_filters",
    "generate_array_field_filters",
    "generate_date_trunc_filters",
    "generate_date_extract_filters",
    "generate_historical_filters",
    "get_advanced_filter_types",
    "DEFAULT_MAX_NESTED_DEPTH",
    "MAX_ALLOWED_NESTED_DEPTH",
    "DEFAULT_CACHE_MAX_SIZE",
    "FIELD_TYPE_TO_FILTER_INPUT",
    # Security
    "FilterSecurityError",
    "validate_regex_pattern",
    "validate_filter_depth",
    "count_filter_clauses",
    "validate_filter_complexity",
    "get_nested_filter_applicator",
    "get_nested_filter_generator",
    "clear_filter_caches",
    "DEFAULT_MAX_REGEX_LENGTH",
    "DEFAULT_MAX_FILTER_DEPTH",
    "DEFAULT_MAX_FILTER_CLAUSES",
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
    "FieldCompareFilterInput",
    "CompareOperatorEnum",
    "DateTruncPrecisionEnum",
    "DateTruncFilterInput",
    "ExtractDateFilterInput",
    "FullTextSearchTypeEnum",
    "FullTextSearchInput",
    # Mixins
    "QuickFilterMixin",
    "IncludeFilterMixin",
    "HistoricalModelMixin",
    "GraphQLMetaIntegrationMixin",
    "SchemaSettingsMixin",
    # Analysis
    "PerformanceAnalyzer",
    "FilterOperation",
    "GroupedFieldFilter",
    "FilterMetadataGenerator",
    # Advanced generators
    "AdvancedFilterGenerator",
    "EnhancedFilterGenerator",
]
