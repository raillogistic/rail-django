"""
Système d'authentification multi-facteurs (MFA) pour Django GraphQL.

Ce module fournit :
- Authentification TOTP (Time-based One-Time Password)
- Codes de récupération
- Authentification par SMS (optionnel)
- Gestion des appareils de confiance
"""

import base64
import logging
import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import graphene
import pyotp
import qrcode
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone as django_timezone
from graphene_django import DjangoObjectType

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


# Models moved to apps.core.models to avoid AppRegistryNotReady errors
# Use lazy imports to defer model access until Django apps are ready
def get_mfa_device_model():
    """Lazy import for MFADevice to avoid AppRegistryNotReady errors."""
    from apps.core.models import MFADevice
    return MFADevice


def get_mfa_backup_code_model():
    """Lazy import for MFABackupCode to avoid AppRegistryNotReady errors."""
    from apps.core.models import MFABackupCode
    return MFABackupCode


def get_trusted_device_model():
    """Lazy import for TrustedDevice to avoid AppRegistryNotReady errors."""
    from apps.core.models import TrustedDevice
    return TrustedDevice


class MFAManager:
    """
    Gestionnaire pour les opérations MFA.
    """

    def __init__(self):
        """Initialise le gestionnaire MFA."""
        self.totp_validity_window = getattr(settings, "MFA_TOTP_VALIDITY_WINDOW", 1)
        self.backup_codes_count = getattr(settings, "MFA_BACKUP_CODES_COUNT", 10)
        self.trusted_device_duration = getattr(
            settings, "MFA_TRUSTED_DEVICE_DURATION", 30
        )  # jours
        self.sms_token_length = getattr(settings, "MFA_SMS_TOKEN_LENGTH", 6)
        self.sms_token_validity = getattr(
            settings, "MFA_SMS_TOKEN_VALIDITY", 300
        )  # 5 minutes
        # In-memory SMS token store: {"userId_deviceId": (token, expires_ts)}
        self._sms_tokens: Dict[str, Tuple[str, float]] = {}

    def setup_totp_device(self, user: "AbstractUser", device_name: str) -> Tuple["MFADevice", str]:
        """
        Configure un appareil TOTP pour l'utilisateur.

        Args:
            user: Utilisateur
            device_name: Nom de l'appareil

        Returns:
            Tuple (appareil MFA, QR code en base64)
        """
        # Générer une clé secrète
        secret_key = pyotp.random_base32()

        # Créer l'appareil MFA
        device = get_mfa_device_model().objects.create(
            user=user,
            device_name=device_name,
            device_type="totp",
            secret_key=secret_key,
            is_active=False,  # Sera activé après vérification
        )

        # Générer le QR code
        qr_code = device.generate_qr_code()

        return device, qr_code

    def verify_and_activate_totp_device(self, device: "MFADevice", token: str) -> bool:
        """
        Vérifie et active un appareil TOTP.

        Args:
            device: Appareil MFA à activer
            token: Token de vérification

        Returns:
            True si l'activation a réussi
        """
        if device.verify_token(token):
            device.is_active = True
            device.last_used = django_timezone.now()
            device.save()

            # Générer les codes de récupération
            self._generate_backup_codes(device)

            return True

        return False

    def setup_sms_device(
        self, user: "AbstractUser", phone_number: str, device_name: str
    ) -> "MFADevice":
        """
        Configure un appareil SMS pour l'utilisateur.

        Args:
            user: Utilisateur
            phone_number: Numéro de téléphone
            device_name: Nom de l'appareil

        Returns:
            Appareil MFA créé
        """
        device = get_mfa_device_model().objects.create(
            user=user,
            device_name=device_name,
            device_type="sms",
            phone_number=phone_number,
            secret_key="",  # Pas de clé secrète pour SMS
            is_active=True,
        )

        return device

    def send_sms_token(self, device: "MFADevice") -> bool:
        """
        Envoie un token SMS à l'utilisateur.

        Args:
            device: Appareil SMS

        Returns:
            True si l'envoi a réussi
        """
        if device.device_type != "sms" or not device.phone_number:
            return False

        # Générer un token aléatoire
        token = "".join(
            [str(secrets.randbelow(10)) for _ in range(self.sms_token_length)]
        )

        # Stocker le token en mémoire (TTL)
        cache_key = f"sms_token_{device.user.id}_{device.id}"
        self._sms_tokens[cache_key] = (
            token,
            django_timezone.now().timestamp() + float(self.sms_token_validity),
        )

        # Envoyer le SMS (implémentation dépendante du fournisseur)
        return self._send_sms(device.phone_number, token)

    def verify_mfa_token(
        self, user: "AbstractUser", token: str, device_id: Optional[int] = None
    ) -> bool:
        """
        Vérifie un token MFA pour l'utilisateur.

        Args:
            user: Utilisateur
            token: Token à vérifier
            device_id: ID de l'appareil spécifique (optionnel)

        Returns:
            True si le token est valide
        """
        devices = user.mfa_devices.filter(is_active=True)

        if device_id:
            devices = devices.filter(id=device_id)

        for device in devices:
            if device.device_type == "sms":
                key = f"sms_token_{user.id}_{device.id}"
                stored = self._sms_tokens.get(key)
                if stored:
                    stored_token, expires_ts = stored
                    if django_timezone.now().timestamp() <= expires_ts and stored_token == token:
                        # consume token
                        self._sms_tokens.pop(key, None)
                        device.last_used = django_timezone.now()
                        device.save()
                        return True
            # Fallback to device's verify for non-SMS or if no stored token
            if device.verify_token(token):
                device.last_used = django_timezone.now()
                device.save()
                return True

        return False

    def is_mfa_required(self, user: "AbstractUser") -> bool:
        """
        Détermine si MFA est requis pour l'utilisateur.

        Args:
            user: Utilisateur

        Returns:
            True si MFA est requis
        """
        # Vérifier si l'utilisateur a des appareils MFA actifs
        has_active_devices = user.mfa_devices.filter(is_active=True).exists()

        # Vérifier la politique MFA globale
        mfa_required_for_all = getattr(settings, "MFA_REQUIRED_FOR_ALL_USERS", False)
        mfa_required_for_staff = getattr(settings, "MFA_REQUIRED_FOR_STAFF", True)

        if mfa_required_for_all:
            return True

        if mfa_required_for_staff and (user.is_staff or user.is_superuser):
            return True

        return has_active_devices

    def is_device_trusted(self, user: "AbstractUser", device_fingerprint: str) -> bool:
        """
        Vérifie si un appareil est de confiance.

        Args:
            user: Utilisateur
            device_fingerprint: Empreinte de l'appareil

        Returns:
            True si l'appareil est de confiance
        """
        try:
            trusted_device = get_trusted_device_model().objects.get(
                user=user, device_fingerprint=device_fingerprint, is_active=True
            )

            if trusted_device.is_expired():
                trusted_device.is_active = False
                trusted_device.save()
                return False

            return True
        except get_trusted_device_model().DoesNotExist:
            return False

    def add_trusted_device(
        self,
        user: "AbstractUser",
        device_fingerprint: str,
        device_name: str,
        ip_address: str,
        user_agent: str,
    ) -> "TrustedDevice":
        """
        Ajoute un appareil de confiance.

        Args:
            user: Utilisateur
            device_fingerprint: Empreinte de l'appareil
            device_name: Nom de l'appareil
            ip_address: Adresse IP
            user_agent: User agent

        Returns:
            Appareil de confiance créé
        """
        expires_at = django_timezone.now() + timedelta(
            days=self.trusted_device_duration
        )

        trusted_device = get_trusted_device_model().objects.create(
            user=user,
            device_fingerprint=device_fingerprint,
            device_name=device_name,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )

        return trusted_device

    def generate_device_fingerprint(self, ip_address: str, user_agent: str) -> str:
        """
        Génère une empreinte d'appareil.

        Args:
            ip_address: Adresse IP
            user_agent: User agent

        Returns:
            Empreinte de l'appareil
        """
        import hashlib

        fingerprint_data = f"{ip_address}:{user_agent}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()

    def get_backup_codes(self, user: "AbstractUser") -> List[str]:
        """
        Récupère les codes de récupération non utilisés de l'utilisateur.

        Args:
            user: Utilisateur

        Returns:
            Liste des codes de récupération
        """
        backup_device = user.mfa_devices.filter(
            device_type="backup", is_active=True
        ).first()

        if not backup_device:
            return []

        backup_codes = backup_device.backup_codes.filter(is_used=False)
        return [code.code for code in backup_codes]

    def regenerate_backup_codes(self, user: "AbstractUser") -> List[str]:
        """
        Régénère les codes de récupération pour l'utilisateur.

        Args:
            user: Utilisateur

        Returns:
            Nouveaux codes de récupération
        """
        # Supprimer les anciens codes
        backup_device = user.mfa_devices.filter(device_type="backup").first()

        if backup_device:
            backup_device.backup_codes.all().delete()
        else:
            backup_device = get_mfa_device_model().objects.create(
                user=user,
                device_name="Codes de récupération",
                device_type="backup",
                secret_key="",
                is_active=True,
            )

        # Générer de nouveaux codes
        return self._generate_backup_codes(backup_device)

    def _generate_backup_codes(self, device: "MFADevice") -> List[str]:
        """
        Génère des codes de récupération pour un appareil.

        Args:
            device: Appareil MFA

        Returns:
            Liste des codes générés
        """
        codes = []

        for _ in range(self.backup_codes_count):
            # Générer un code de 8 caractères
            code = "".join([str(secrets.randbelow(10)) for _ in range(8)])
            codes.append(code)

            get_mfa_backup_code_model().objects.create(device=device, code=code)

        return codes

    def _send_sms(self, phone_number: str, token: str) -> bool:
        """
        Envoie un SMS avec le token.

        Args:
            phone_number: Numéro de téléphone
            token: Token à envoyer

        Returns:
            True si l'envoi a réussi
        """
        # Cette méthode doit être implémentée selon le fournisseur SMS choisi
        # (Twilio, AWS SNS, etc.)

        try:
            # Exemple avec Twilio (nécessite configuration)
            sms_provider = getattr(settings, "MFA_SMS_PROVIDER", None)

            if sms_provider == "twilio":
                return self._send_sms_twilio(phone_number, token)
            elif sms_provider == "aws_sns":
                return self._send_sms_aws(phone_number, token)
            else:
                # Mode développement - logger le token
                logger.info(f"Token SMS pour {phone_number}: {token}")
                return True

        except Exception as e:
            logger.error(f"Erreur lors de l'envoi SMS: {e}")
            return False

    def _send_sms_twilio(self, phone_number: str, token: str) -> bool:
        """
        Envoie un SMS via Twilio.

        Args:
            phone_number: Numéro de téléphone
            token: Token à envoyer

        Returns:
            True si l'envoi a réussi
        """
        try:
            from twilio.rest import Client

            account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
            auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
            from_number = getattr(settings, "TWILIO_FROM_NUMBER", "")

            client = Client(account_sid, auth_token)

            message = client.messages.create(
                body=f"Votre code de vérification: {token}",
                from_=from_number,
                to=phone_number,
            )

            return message.sid is not None

        except Exception as e:
            logger.error(f"Erreur Twilio: {e}")
            return False

    def _send_sms_aws(self, phone_number: str, token: str) -> bool:
        """
        Envoie un SMS via AWS SNS.

        Args:
            phone_number: Numéro de téléphone
            token: Token à envoyer

        Returns:
            True si l'envoi a réussi
        """
        try:
            import boto3

            sns = boto3.client("sns")

            response = sns.publish(
                PhoneNumber=phone_number, Message=f"Votre code de vérification: {token}"
            )

            return response["ResponseMetadata"]["HTTPStatusCode"] == 200

        except Exception as e:
            logger.error(f"Erreur AWS SNS: {e}")
            return False


# Instance globale du gestionnaire MFA
mfa_manager = MFAManager()


# Types GraphQL pour MFA


def get_mfa_device_type():
    """Factory function to create MFADeviceType with proper model reference."""

    class MFADeviceType(DjangoObjectType):
        """Type GraphQL pour les appareils MFA."""

        class Meta:
            model = get_mfa_device_model()
            fields = (
                "id",
                "device_name",
                "device_type",
                "is_active",
                "is_primary",
                "created_at",
                "last_used",
            )

    return MFADeviceType


def get_trusted_device_type():
    """Factory function to create TrustedDeviceType with proper model reference."""

    class TrustedDeviceType(DjangoObjectType):
        """Type GraphQL pour les appareils de confiance."""

        class Meta:
            model = get_trusted_device_model()
            fields = (
                "id",
                "device_name",
                "ip_address",
                "created_at",
                "expires_at",
                "is_active",
            )

    return TrustedDeviceType


# Create lazy references that will be resolved when needed
_mfa_device_type = None
_trusted_device_type = None


def MFADeviceType():
    """Lazy MFADeviceType that resolves the model when Django apps are ready."""
    global _mfa_device_type
    if _mfa_device_type is None:
        _mfa_device_type = get_mfa_device_type()
    return _mfa_device_type


def TrustedDeviceType():
    """Lazy TrustedDeviceType that resolves the model when Django apps are ready."""
    global _trusted_device_type
    if _trusted_device_type is None:
        _trusted_device_type = get_trusted_device_type()
    return _trusted_device_type


class SetupTOTPMutation(graphene.Mutation):
    """Mutation pour configurer TOTP."""

    class Arguments:
        device_name = graphene.String(required=True)

    success = graphene.Boolean()
    device_id = graphene.Int()
    qr_code = graphene.String()
    secret_key = graphene.String()
    message = graphene.String()

    def mutate(self, info, device_name):
        user = info.context.user

        if not user.is_authenticated:
            return SetupTOTPMutation(success=False, message="Authentification requise")

        try:
            device, qr_code = mfa_manager.setup_totp_device(user, device_name)

            return SetupTOTPMutation(
                success=True,
                device_id=device.id,
                qr_code=qr_code,
                secret_key=device.secret_key,
                message="Appareil TOTP configuré avec succès",
            )
        except Exception as e:
            return SetupTOTPMutation(success=False, message=str(e))


class VerifyTOTPMutation(graphene.Mutation):
    """Mutation pour vérifier et activer TOTP."""

    class Arguments:
        device_id = graphene.Int(required=True)
        token = graphene.String(required=True)

    success = graphene.Boolean()
    backup_codes = graphene.List(graphene.String)
    message = graphene.String()

    def mutate(self, info, device_id, token):
        user = info.context.user

        if not user.is_authenticated:
            return VerifyTOTPMutation(success=False, message="Authentification requise")

        try:
            device = get_mfa_device_model().objects.get(id=device_id, user=user)

            if mfa_manager.verify_and_activate_totp_device(device, token):
                backup_codes = mfa_manager.get_backup_codes(user)

                return VerifyTOTPMutation(
                    success=True,
                    backup_codes=backup_codes,
                    message="Appareil TOTP activé avec succès",
                )
            else:
                return VerifyTOTPMutation(success=False, message="Token invalide")

        except get_mfa_device_model().DoesNotExist:
            return VerifyTOTPMutation(success=False, message="Appareil non trouvé")
        except Exception as e:
            return VerifyTOTPMutation(success=False, message=str(e))


class MFAMutations(graphene.ObjectType):
    """Mutations MFA."""

    setup_totp = SetupTOTPMutation.Field()
    verify_totp = VerifyTOTPMutation.Field()


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
