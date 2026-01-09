"""
Module de sécurité pour Django GraphQL.

Ce module fournit des fonctionnalités de sécurité avancées :
- Validation et assainissement des entrées
- Contrôle d'accès basé sur les rôles (RBAC)
- Permissions au niveau des champs
- Sécurité spécifique à GraphQL
- Journalisation d'audit
"""

from .audit_logging import (
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
from .input_validation import (
    GraphQLInputSanitizer,
    InputValidator,
    ValidationResult,
    ValidationSeverity,
    validate_input,
)
from .rbac import (
    PermissionContext,
    PermissionScope,
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
    'ValidationResult',
    'InputValidator',
    'GraphQLInputSanitizer',
    'validate_input',

    # RBAC
    'RoleType',
    'PermissionScope',
    'RoleDefinition',
    'PermissionContext',
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
