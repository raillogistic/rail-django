"""Django GraphQL Auto-Generation Extensions Package.

This package provides advanced extensions for Django GraphQL Auto-Generation including:
- JWT-based authentication system with GraphQL mutations
- Multi-factor authentication (MFA) with TOTP, SMS, and backup codes
- Comprehensive audit logging for security events
- Model data export functionality with JWT protection
- Model metadata schema for rich frontend interfaces
- Advanced security features and middleware

The extensions are designed to work seamlessly with the core GraphQL auto-generation
functionality while providing enterprise-grade security and monitoring capabilities.
"""

# Core authentication system
# TOTPSetupMutation,
# TOTPVerifyMutation,
# SMSSetupMutation,
# SMSVerifyMutation,
# BackupCodeGenerateMutation,
# BackupCodeVerifyMutation,
# TrustedDeviceManager,
# Audit logging system
from .audit import AuditLogger  # AuditLogEntry,

# SecurityEvent,
# get_audit_logger,
from .auth import (  # ChangePasswordMutation,
    AuthPayload,
    JWTManager,
    LoginMutation,
    LogoutMutation,
    RefreshTokenMutation,
    RegisterMutation,
    UserType,
)

# Authentication decorators for Django views
from .auth_decorators import (
    get_user_from_jwt,
    jwt_optional,
    jwt_required,
    require_permissions,
)

# Model export functionality (JWT protected)
from .exporting import (
    ExportJobDownloadView,
    ExportJobStatusView,
    ExportView,
    ModelExporter,
    export_model_to_csv,
    export_model_to_excel,
)

# Model metadata schema for rich frontend interfaces
from .metadata import (
    FieldMetadataType,
    ModelMetadataExtractor,
    ModelMetadataQuery,
    ModelMetadataType,
    RelationshipMetadataType,
)

# Model schema V2 for rich frontend interfaces
from .metadata_v2 import (
    FieldSchemaType,
    ModelSchemaExtractor,
    ModelSchemaQueryV2,
    ModelSchemaType,
    RelationshipSchemaType,
)

# PDF templating helpers
from .templating import (
    PdfTemplateView,
    model_pdf_template,
    template_registry,
    template_urlpatterns,
)

# Excel export templating helpers
from .excel import (
    ExcelTemplateView,
    ExcelTemplateCatalogView,
    model_excel_template,
    excel_template,
    excel_template_registry,
    excel_urlpatterns,
    render_excel,
)

# Multi-factor authentication
from .mfa import MFAManager
from .multitenancy import (
    TenantContextMiddleware,
    TenantManager,
    TenantMixin,
    TenantQuerySet,
)
from .tasks import (
    TaskExecution,
    TaskExecutionHandle,
    TaskQuery,
    TaskStatus,
    TaskStatusView,
    get_task_settings,
    get_task_subscription_field,
    get_task_urls,
    task_mutation,
    tasks_enabled,
)

__all__ = [
    # Authentication
    "JWTManager",
    "AuthPayload",
    "LoginMutation",
    "RegisterMutation",
    "RefreshTokenMutation",
    "LogoutMutation",
    "ChangePasswordMutation",
    "UserType",
    # Authentication decorators
    "jwt_required",
    "jwt_optional",
    "get_user_from_jwt",
    "require_permissions",
    # "TOTPSetupMutation",
    # "TOTPVerifyMutation",
    # "SMSSetupMutation",
    # "SMSVerifyMutation",
    # "BackupCodeGenerateMutation",
    # "BackupCodeVerifyMutation",
    # "TrustedDeviceManager",
    # Audit logging
    "AuditLogger",
    # "SecurityEvent",
    # "AuditLogEntry",
    # "get_audit_logger",
    # Model export (JWT protected)
    "ExportView",
    "ExportJobStatusView",
    "ExportJobDownloadView",
    "ModelExporter",
    "export_model_to_csv",
    "export_model_to_excel",
    # Model metadata schema
    "ModelMetadataQuery",
    "ModelMetadataType",
    "FieldMetadataType",
    "RelationshipMetadataType",
    "ModelMetadataExtractor",
    # Model schema V2
    "ModelSchemaQueryV2",
    "ModelSchemaType",
    "FieldSchemaType",
    "RelationshipSchemaType",
    "ModelSchemaExtractor",
    # PDF templating
    "PdfTemplateView",
    "model_pdf_template",
    "template_registry",
    "template_urlpatterns",
    # Excel export templating
    "ExcelTemplateView",
    "ExcelTemplateCatalogView",
    "model_excel_template",
    "excel_template",
    "excel_template_registry",
    "excel_urlpatterns",
    "render_excel",
    # Multi-factor authentication
    "MFAManager",
    # Multi-tenancy
    "TenantContextMiddleware",
    "TenantManager",
    "TenantMixin",
    "TenantQuerySet",
    # Tasks
    "TaskExecution",
    "TaskExecutionHandle",
    "TaskQuery",
    "TaskStatus",
    "TaskStatusView",
    "get_task_settings",
    "get_task_subscription_field",
    "get_task_urls",
    "task_mutation",
    "tasks_enabled",
]
