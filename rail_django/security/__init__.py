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
    'PolicyManager',
    'policy_manager',

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
