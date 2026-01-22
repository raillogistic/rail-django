"""
MFA GraphQL types.
"""

from graphene_django import DjangoObjectType
from .models import MFADevice, TrustedDevice


class MFADeviceType(DjangoObjectType):
    """Type GraphQL pour les appareils MFA."""

    class Meta:
        model = MFADevice
        fields = (
            "id",
            "device_name",
            "device_type",
            "is_active",
            "is_primary",
            "created_at",
            "last_used",
        )


class TrustedDeviceType(DjangoObjectType):
    """Type GraphQL pour les appareils de confiance."""

    class Meta:
        model = TrustedDevice
        fields = (
            "id",
            "device_name",
            "ip_address",
            "created_at",
            "expires_at",
            "is_active",
        )
