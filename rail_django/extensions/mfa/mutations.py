"""
MFA GraphQL mutations.
"""

import graphene
from .manager import mfa_manager
from .models import MFADevice


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
            device = MFADevice.objects.get(id=device_id, user=user)

            if mfa_manager.verify_and_activate_totp_device(device, token):
                backup_codes = mfa_manager.get_backup_codes(user)

                return VerifyTOTPMutation(
                    success=True,
                    backup_codes=backup_codes,
                    message="Appareil TOTP activé avec succès",
                )
            else:
                return VerifyTOTPMutation(success=False, message="Token invalide")

        except MFADevice.DoesNotExist:
            return VerifyTOTPMutation(success=False, message="Appareil non trouvé")
        except Exception as e:
            return VerifyTOTPMutation(success=False, message=str(e))


class MFAMutations(graphene.ObjectType):
    """Mutations MFA."""

    setup_totp = SetupTOTPMutation.Field()
    verify_totp = VerifyTOTPMutation.Field()
