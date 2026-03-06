"""
Security module for Django GraphQL.

This module provides advanced security features:
- Input validation and sanitization
- Role-Based Access Control (RBAC)
- Field-level permissions
- GraphQL-specific security
- Unified audit logging (Security Events)
"""

from .api import security, SecurityAPI
from .middleware.context import get_security_context
from .context import SecurityContext, Actor
from .events.types import (
    SecurityEvent,
    EventType,
    EventCategory,
    Severity,
    Outcome,
    Resource,
)
from .events.builder import event, EventBuilder
from .events.bus import get_event_bus, EventBus
from .anomaly.detector import get_anomaly_detector, AnomalyDetector

from .field_permissions import (
    FieldAccessLevel,
    FieldContext,
    FieldPermissionManager,
    FieldPermissionRule,
    FieldVisibility,
    field_permission_manager,
    field_permission_required,
    mask_sensitive_fields,
)
from .graphql import (
    GraphQLSecurityAnalyzer,
    QueryAnalysisResult,
    QueryComplexityValidationRule,
    SecurityConfig,
    SecurityThreatLevel,
    create_security_middleware,
    default_security_config,
    require_introspection_permission,
    security_analyzer,
)
from .frontend_routes import (
    ALLOWED_TARGET_TYPES,
    FrontendRouteAccessRegistry,
    FrontendRouteAccessRule,
    build_frontend_route_access_rule,
    frontend_route_access_registry,
    load_frontend_route_access_from_payload,
)
from .validation import (
    GraphQLInputSanitizer,
    InputValidator,
    ValidationReport,
    ValidationResult,
    ValidationSeverity,
    validate_input,
)
from .policies import (
    AccessPolicy,
    AttributeCondition,
    PolicyContext,
    PolicyEffect,
    PolicyManager,
    policy_manager,
)
from .rbac import (
    PermissionExplanation,
    PermissionContext,
    PermissionScope,
    PolicyDecisionDetail,
    RoleDefinition,
    RoleManager,
    RoleType,
    require_permission,
    require_role,
    role_manager,
)
from .abac import (
    ABACContext,
    ABACDecision,
    ABACEngine,
    ABACManager,
    ABACPolicy,
    ActionAttributeProvider,
    AttributeSet,
    BaseAttributeProvider,
    ConditionOperator,
    EnvironmentAttributeProvider,
    MatchCondition,
    ResourceAttributeProvider,
    SubjectAttributeProvider,
    abac_engine,
    abac_manager,
    require_attributes,
)
from .hybrid import CombinationStrategy, HybridDecision, HybridPermissionEngine, hybrid_engine

__all__ = [
    # New Security API & Events
    "security",
    "SecurityAPI",
    "SecurityContext",
    "get_security_context",
    "Actor",
    "SecurityEvent",
    "EventType",
    "EventCategory",
    "Severity",
    "Outcome",
    "Resource",
    "event",
    "EventBuilder",
    "get_event_bus",
    "EventBus",

    # Input Validation
    'ValidationSeverity',
    'ValidationReport',
    'ValidationResult',
    'InputValidator',
    'GraphQLInputSanitizer',
    'validate_input',

    # RBAC
    'RoleType',
    'PermissionScope',
    'RoleDefinition',
    'PermissionContext',
    'PermissionExplanation',
    'PolicyDecisionDetail',
    'RoleManager',
    'role_manager',
    'require_role',
    'require_permission',
    'ALLOWED_TARGET_TYPES',
    'FrontendRouteAccessRule',
    'FrontendRouteAccessRegistry',
    'frontend_route_access_registry',
    'build_frontend_route_access_rule',
    'load_frontend_route_access_from_payload',

    # Field Permissions
    'FieldAccessLevel',
    'FieldVisibility',
    'FieldPermissionRule',
    'FieldContext',
    'FieldPermissionManager',
    'field_permission_manager',
    'field_permission_required',
    'mask_sensitive_fields',

    # Access policies
    'PolicyEffect',
    'PolicyContext',
    'AccessPolicy',
    'AttributeCondition',
    'PolicyManager',
    'policy_manager',

    # ABAC
    "ABACPolicy",
    "ABACDecision",
    "ABACContext",
    "AttributeSet",
    "MatchCondition",
    "ConditionOperator",
    "ABACEngine",
    "abac_engine",
    "BaseAttributeProvider",
    "SubjectAttributeProvider",
    "ResourceAttributeProvider",
    "EnvironmentAttributeProvider",
    "ActionAttributeProvider",
    "require_attributes",
    "ABACManager",
    "abac_manager",

    # Hybrid
    "CombinationStrategy",
    "HybridDecision",
    "HybridPermissionEngine",
    "hybrid_engine",

    # GraphQL Security
    'SecurityThreatLevel',
    'QueryAnalysisResult',
    'SecurityConfig',
    'GraphQLSecurityAnalyzer',
    'QueryComplexityValidationRule',
    'create_security_middleware',
    'require_introspection_permission',
    'default_security_config',
    'security_analyzer',
]
