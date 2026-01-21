"""
Module de sécurité pour Django GraphQL.

Ce module fournit des fonctionnalités de sécurité avancées :
- Validation et assainissement des entrées
- Contrôle d'accès basé sur les rôles (RBAC)
- Permissions au niveau des champs
- Sécurité spécifique à GraphQL
- Journalisation d'audit
"""

from .audit import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    AuditSeverity,
    audit_data_modification,
    audit_graphql_operation,
    audit_logger,
)
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
from .graphql_security import (
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

    # Audit Logging
    'AuditEventType',
    'AuditSeverity',
    'AuditEvent',
    'AuditLogger',
    'audit_logger',
    'audit_graphql_operation',
    'audit_data_modification',
]
