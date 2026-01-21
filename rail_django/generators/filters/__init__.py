"""
Filters Package for Rail Django.

This package provides nested GraphQL filter input types following the Prisma/Hasura
pattern, with typed filter inputs for each field type and built-in security features.

Package Structure:
    - generator: NestedFilterInputGenerator class for generating filter inputs
    - generator_utils: Utility functions for filter generation
    - security: Security validation functions (regex, depth, complexity)
    - types: GraphQL InputObjectType definitions for filtering
        - base_types: String, Int, Float, Boolean, ID, UUID
        - date_types: Date, DateTime
        - advanced_types: JSON, Array, Count
    - mixins: Reusable mixin classes for filter functionality
        - QuickFilterMixin: Multi-field search
        - IncludeFilterMixin: ID union filtering
        - HistoricalModelMixin: django-simple-history support
        - GraphQLMetaIntegrationMixin: GraphQLMeta integration
        - SchemaSettingsMixin: Schema settings integration
    - analysis: Performance analysis and filter metadata
        - PerformanceAnalyzer: Query performance analysis
        - FilterOperation: Single filter operation representation
        - GroupedFieldFilter: Grouped filter for UI builders
        - FilterMetadataGenerator: Metadata generation
    - advanced: Legacy-compatible filter generators
        - AdvancedFilterGenerator: Full-featured filter generator
        - EnhancedFilterGenerator: Metadata-focused generator

Example Usage:
    from rail_django.generators.filters import (
        NestedFilterInputGenerator,
        FilterSecurityError,
        validate_filter_complexity,
        StringFilterInput,
        DateTimeFilterInput,
        # Mixins
        QuickFilterMixin,
        IncludeFilterMixin,
        # Analysis
        PerformanceAnalyzer,
        FilterMetadataGenerator,
        # Advanced generators
        AdvancedFilterGenerator,
        EnhancedFilterGenerator,
    )
"""

# Generator exports
from .generator import (
    NestedFilterInputGenerator,
    generate_where_input_for_model,
)

# Applicator exports
from .applicator import (
    NestedFilterApplicator,
    apply_where_filter,
)

# Generator utility exports
from .generator_utils import (
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
)

# Security exports
from .security import (
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
)

# Filter type exports
from .types import (
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
)

# Mixin exports
from .mixins import (
    QuickFilterMixin,
    IncludeFilterMixin,
    HistoricalModelMixin,
    GraphQLMetaIntegrationMixin,
    SchemaSettingsMixin,
)

# Analysis exports
from .analysis import (
    PerformanceAnalyzer,
    FilterOperation,
    GroupedFieldFilter,
    FilterMetadataGenerator,
)

# Advanced generator exports
from .advanced import (
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
    "_filter_generator_registry",
    "_filter_applicator_registry",
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
