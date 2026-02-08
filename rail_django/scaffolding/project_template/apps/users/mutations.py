import graphene
import json
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from graphene.types.generic import GenericScalar
from .models import PasswordResetOTP, UserSettings
from django.conf import settings
import random
import string
import datetime

User = get_user_model()


class SimplePayload(graphene.ObjectType):
    ok = graphene.Boolean(required=True)
    errors = graphene.List(graphene.String)


class UpsertUserTableConfigPayload(graphene.ObjectType):
    ok = graphene.Boolean(required=True)
    errors = graphene.List(graphene.String)
    settings_id = graphene.ID()
    table_configs = GenericScalar()
    table_config = GenericScalar()


def _decode_json_object(value, field_name):
    if value is None:
        return {}

    decoded = value
    if isinstance(value, str):
        raw_value = value.strip()
        if not raw_value:
            return {}
        try:
            decoded = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} must be valid JSON.") from exc

    if not isinstance(decoded, dict):
        raise ValueError(f"{field_name} must be a JSON object.")

    return decoded


class ChangePasswordMutation(graphene.Mutation):
    class Arguments:
        old_password = graphene.String(required=True)
        new_password = graphene.String(required=True)

    Output = SimplePayload

    def mutate(self, info, old_password, new_password):
        user = info.context.user
        if not user or not user.is_authenticated:
            return SimplePayload(ok=False, errors=["Vous devez être connecté."])

        if not user.check_password(old_password):
            return SimplePayload(
                ok=False, errors=["L'ancien mot de passe est incorrect."]
            )

        try:
            validate_password(new_password, user)
        except ValidationError as e:
            return SimplePayload(ok=False, errors=e.messages)

        user.set_password(new_password)
        user.save()

        return SimplePayload(ok=True, errors=[])


class RequestPasswordResetMutation(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)

    Output = SimplePayload

    def mutate(self, info, email):
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Return success even if user not found to prevent enumeration
            return SimplePayload(ok=True, errors=[])

        # Generate code
        code = "".join(random.choices(string.digits, k=6))
        expires_at = timezone.now() + datetime.timedelta(minutes=15)

        # Invalidate existing codes
        PasswordResetOTP.objects.filter(user=user, is_used=False).update(is_used=True)

        # Create new code
        PasswordResetOTP.objects.create(user=user, code=code, expires_at=expires_at)

        # Send email
        context = {
            "code": code,
            "site_name": "Rail Logistics",
        }
        message = render_to_string(
            "registration/password_reset_email_code.txt", context
        )

        try:
            send_mail(
                "Réinitialisation de mot de passe",
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
        except Exception as e:
            return SimplePayload(
                ok=False, errors=[f"Erreur lors de l'envoi de l'email: {str(e)}"]
            )

        return SimplePayload(ok=True, errors=[])


class ValidateResetCodeMutation(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)
        code = graphene.String(required=True)

    Output = SimplePayload

    def mutate(self, info, email, code):
        try:
            user = User.objects.get(email=email)
            otp = PasswordResetOTP.objects.filter(
                user=user, code=code, is_used=False, expires_at__gt=timezone.now()
            ).first()

            if otp:
                return SimplePayload(ok=True, errors=[])
            else:
                return SimplePayload(ok=False, errors=["Code invalide ou expiré."])
        except User.DoesNotExist:
            return SimplePayload(ok=False, errors=["Utilisateur non trouvé."])


class ConfirmPasswordResetMutation(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)
        code = graphene.String(required=True)
        new_password = graphene.String(required=True)

    Output = SimplePayload

    def mutate(self, info, email, code, new_password):
        try:
            user = User.objects.get(email=email)
            otp = PasswordResetOTP.objects.filter(
                user=user, code=code, is_used=False, expires_at__gt=timezone.now()
            ).first()

            if not otp:
                return SimplePayload(ok=False, errors=["Code invalide ou expiré."])

            try:
                validate_password(new_password, user)
            except ValidationError as e:
                return SimplePayload(ok=False, errors=e.messages)

            user.set_password(new_password)
            user.save()

            # Mark code as used
            otp.is_used = True
            otp.save()

            # Mark all other codes as used
            PasswordResetOTP.objects.filter(user=user).update(is_used=True)

            return SimplePayload(ok=True, errors=[])
        except User.DoesNotExist:
            return SimplePayload(ok=False, errors=["Utilisateur non trouvé."])


class UpsertUserTableConfigMutation(graphene.Mutation):
    class Arguments:
        key = graphene.String(required=True)
        table_config = GenericScalar(required=True)

    Output = UpsertUserTableConfigPayload

    def mutate(self, info, key, table_config):
        user = info.context.user
        if not user or not user.is_authenticated:
            return UpsertUserTableConfigPayload(
                ok=False, errors=["Authentication required."]
            )

        table_key = (key or "").strip()
        if not table_key:
            return UpsertUserTableConfigPayload(
                ok=False, errors=["Parameter 'key' is required."]
            )

        try:
            parsed_config = _decode_json_object(table_config, "tableConfig")
        except ValueError as exc:
            return UpsertUserTableConfigPayload(ok=False, errors=[str(exc)])

        settings_obj, _ = UserSettings.objects.get_or_create(user=user)

        try:
            current_configs = _decode_json_object(
                settings_obj.table_configs, "tableConfigs"
            )
        except ValueError:
            current_configs = {}

        current_configs[table_key] = parsed_config
        settings_obj.table_configs = current_configs
        settings_obj.save(update_fields=["table_configs"])

        return UpsertUserTableConfigPayload(
            ok=True,
            errors=[],
            settings_id=str(settings_obj.pk),
            table_configs=current_configs,
            table_config=parsed_config,
        )


class UsersMutations(graphene.ObjectType):
    change_password = ChangePasswordMutation.Field()
    request_password_reset = RequestPasswordResetMutation.Field()
    validate_reset_code = ValidateResetCodeMutation.Field()
    confirm_password_reset = ConfirmPasswordResetMutation.Field()
    upsert_user_table_config = UpsertUserTableConfigMutation.Field()
