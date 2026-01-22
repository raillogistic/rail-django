"""
MFA GraphQL queries.
"""

import graphene
from .manager import mfa_manager
from .types import MFADeviceType, TrustedDeviceType


class MFAQueries(graphene.ObjectType):
    """Requêtes MFA."""

    mfa_devices = graphene.List(MFADeviceType)
    trusted_devices = graphene.List(TrustedDeviceType)
    backup_codes = graphene.List(graphene.String)

    def resolve_mfa_devices(self, info):
        user = info.context.user
        if not user.is_authenticated:
            return []
        return user.mfa_devices.filter(is_active=True)

    def resolve_trusted_devices(self, info):
        user = info.context.user
        if not user.is_authenticated:
            return []
        return user.trusted_devices.filter(is_active=True)

    def resolve_backup_codes(self, info):
        user = info.context.user
        if not user.is_authenticated:
            return []
        return mfa_manager.get_backup_codes(user)
