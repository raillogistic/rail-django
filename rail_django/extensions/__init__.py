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
# AuditLogger, AuditLogEntry, SecurityEvent, get_audit_logger
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
from .auth.decorators import (
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

# Model schema for rich frontend interfaces
from .metadata import (
    FieldSchemaType,
    ModelSchemaExtractor,
    ModelSchemaQuery,
    ModelSchemaType,
    RelationshipSchemaType,
)

# Form API extension
from .form import (
    FormConfigExtractor,
    ModelFormContractExtractor,
    FormConfigType,
    FormDataType,
    FormQuery,
    ModelFormContractType,
    FieldConfigType as FormFieldConfigType,
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
from .mfa import (
    MFAManager,
    MFADevice,
    MFABackupCode,
    TrustedDevice,
    MFAMutations,
    SetupTOTPMutation,
    VerifyTOTPMutation,
    MFAQueries,
    MFADeviceType,
    TrustedDeviceType,
)
from .multitenancy import (
    TenantContextMiddleware,
    TenantManager,
    TenantMixin,
    TenantQuerySet,
)
try:
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

    _TASK_EXPORTS = [
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
except ImportError:
    _TASK_EXPORTS = []

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
    # Audit logging
    # "AuditLogger",
    # Model export (JWT protected)
    "ExportView",
    "ExportJobStatusView",
    "ExportJobDownloadView",
    "ModelExporter",
    "export_model_to_csv",
    "export_model_to_excel",
    # Model schema
    "ModelSchemaQuery",
    "ModelSchemaType",
    "FieldSchemaType",
    "RelationshipSchemaType",
    "ModelSchemaExtractor",
    # Form API
    "FormQuery",
    "FormConfigExtractor",
    "ModelFormContractExtractor",
    "FormConfigType",
    "FormDataType",
    "ModelFormContractType",
    "FormFieldConfigType",
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
    "MFADevice",
    "MFABackupCode",
    "TrustedDevice",
    "MFAMutations",
    "SetupTOTPMutation",
    "VerifyTOTPMutation",
    "MFAQueries",
    "MFADeviceType",
    "TrustedDeviceType",
    # Multi-tenancy
    "TenantContextMiddleware",
    "TenantManager",
    "TenantMixin",
    "TenantQuerySet",
]

__all__.extend(_TASK_EXPORTS)
