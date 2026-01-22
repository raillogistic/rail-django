"""
MFA database models.
"""

import base64
from io import BytesIO
from typing import TYPE_CHECKING, Any, Optional

import pyotp
import qrcode
from django.conf import settings
from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class MFADevice(models.Model):
    """
    Appareil d'authentification multi-facteurs.
    """

    DEVICE_TYPES = (
        ("totp", "TOTP (Google Authenticator)"),
        ("sms", "SMS"),
        ("backup", "Codes de récupération"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mfa_devices",
        verbose_name="Utilisateur",
    )
    device_name = models.CharField(max_length=100, verbose_name="Nom de l'appareil")
    device_type = models.CharField(
        max_length=20, choices=DEVICE_TYPES, verbose_name="Type d'appareil"
    )
    secret_key = models.CharField(
        max_length=100, blank=True, verbose_name="Clé secrète"
    )
    phone_number = models.CharField(
        max_length=30, blank=True, verbose_name="Numéro de téléphone"
    )
    is_active = models.BooleanField(default=False, verbose_name="Est actif")
    is_primary = models.BooleanField(default=False, verbose_name="Appareil principal")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    last_used = models.DateTimeField(
        null=True, blank=True, verbose_name="Dernière utilisation"
    )

    class Meta:
        app_label = "rail_django"
        db_table = "rail_django_mfadevice"
        verbose_name = "Appareil MFA"
        verbose_name_plural = "Appareils MFA"

    def __str__(self) -> str:
        return f"{self.device_name} ({self.get_device_type_display()})"

    def verify_token(self, token: str) -> bool:
        """Vérifie un token TOTP."""
        if self.device_type != "totp" or not self.secret_key:
            return False

        totp = pyotp.TOTP(self.secret_key)
        return totp.verify(token)

    def generate_qr_code(self) -> str:
        """Génère un QR code pour l'appareil TOTP en base64."""
        if self.device_type != "totp":
            return ""

        issuer_name = getattr(settings, "MFA_ISSUER_NAME", "Rail Django")
        totp = pyotp.TOTP(self.secret_key)
        provisioning_uri = totp.provisioning_uri(
            name=self.user.email, issuer_name=issuer_name
        )

        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()


class MFABackupCode(models.Model):
    """
    Code de récupération pour MFA.
    """

    device = models.ForeignKey(
        MFADevice,
        on_delete=models.CASCADE,
        related_name="backup_codes",
        verbose_name="Appareil MFA",
    )
    code = models.CharField(max_length=20, verbose_name="Code de récupération")
    is_used = models.BooleanField(default=False, verbose_name="Est utilisé")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")

    class Meta:
        app_label = "rail_django"
        db_table = "rail_django_mfabackupcode"
        verbose_name = "Code de récupération"
        verbose_name_plural = "Codes de récupération"

    def __str__(self) -> str:
        return f"Code pour {self.device.user.email}"


class TrustedDevice(models.Model):
    """
    Appareil de confiance pour l'utilisateur.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trusted_devices",
        verbose_name="Utilisateur",
    )
    device_fingerprint = models.CharField(
        max_length=255, db_index=True, verbose_name="Empreinte de l'appareil"
    )
    device_name = models.CharField(max_length=100, verbose_name="Nom de l'appareil")
    ip_address = models.GenericIPAddressField(verbose_name="Adresse IP")
    user_agent = models.TextField(verbose_name="User agent")
    expires_at = models.DateTimeField(verbose_name="Expire le")
    is_active = models.BooleanField(default=True, verbose_name="Est actif")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")

    class Meta:
        app_label = "rail_django"
        db_table = "rail_django_trusteddevice"
        verbose_name = "Appareil de confiance"
        verbose_name_plural = "Appareils de confiance"

    def __str__(self) -> str:
        return f"{self.device_name} ({self.user.email})"

    def is_expired(self) -> bool:
        """Vérifie si l'appareil de confiance est expiré."""
        return timezone.now() > self.expires_at
