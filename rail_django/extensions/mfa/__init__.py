"""
MFA extension package for Rail Django.
"""

from .manager import MFAManager, mfa_manager
from .models import MFADevice, MFABackupCode, TrustedDevice
from .mutations import MFAMutations, SetupTOTPMutation, VerifyTOTPMutation
from .queries import MFAQueries
from .types import MFADeviceType, TrustedDeviceType

__all__ = [
    "MFAManager",
    "mfa_manager",
    "MFADevice",
    "MFABackupCode",
    "TrustedDevice",
    "MFAMutations",
    "SetupTOTPMutation",
    "VerifyTOTPMutation",
    "MFAQueries",
    "MFADeviceType",
    "TrustedDeviceType",
]
