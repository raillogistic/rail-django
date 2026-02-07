import datetime
import random
import string

import graphene
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from .models import PasswordResetOTP

User = get_user_model()


class SimplePayload(graphene.ObjectType):
    ok = graphene.Boolean(required=True)
    errors = graphene.List(graphene.String)


class ChangePasswordMutation(graphene.Mutation):
    class Arguments:
        old_password = graphene.String(required=True)
        new_password = graphene.String(required=True)

    Output = SimplePayload

    def mutate(self, info, old_password, new_password):
        user = info.context.user
        if not user or not user.is_authenticated:
            return SimplePayload(ok=False, errors=["Authentication required."])

        if not user.check_password(old_password):
            return SimplePayload(ok=False, errors=["Old password is incorrect."])

        try:
            validate_password(new_password, user)
        except ValidationError as exc:
            return SimplePayload(ok=False, errors=exc.messages)

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
            # Avoid user enumeration.
            return SimplePayload(ok=True, errors=[])

        code = "".join(random.choices(string.digits, k=6))
        expires_at = timezone.now() + datetime.timedelta(minutes=15)

        PasswordResetOTP.objects.filter(user=user, is_used=False).update(is_used=True)
        PasswordResetOTP.objects.create(user=user, code=code, expires_at=expires_at)

        context = {
            "code": code,
            "site_name": "Rail Django",
        }
        message = render_to_string("registration/password_reset_email_code.txt", context)

        try:
            send_mail(
                "Password reset code",
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
        except Exception as exc:
            return SimplePayload(ok=False, errors=[f"Email sending failed: {exc}"])

        return SimplePayload(ok=True, errors=[])


class ValidateResetCodeMutation(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)
        code = graphene.String(required=True)

    Output = SimplePayload

    def mutate(self, info, email, code):
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return SimplePayload(ok=False, errors=["User not found."])

        otp = PasswordResetOTP.objects.filter(
            user=user,
            code=code,
            is_used=False,
            expires_at__gt=timezone.now(),
        ).first()
        if not otp:
            return SimplePayload(ok=False, errors=["Invalid or expired code."])
        return SimplePayload(ok=True, errors=[])


class ConfirmPasswordResetMutation(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)
        code = graphene.String(required=True)
        new_password = graphene.String(required=True)

    Output = SimplePayload

    def mutate(self, info, email, code, new_password):
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return SimplePayload(ok=False, errors=["User not found."])

        otp = PasswordResetOTP.objects.filter(
            user=user,
            code=code,
            is_used=False,
            expires_at__gt=timezone.now(),
        ).first()
        if not otp:
            return SimplePayload(ok=False, errors=["Invalid or expired code."])

        try:
            validate_password(new_password, user)
        except ValidationError as exc:
            return SimplePayload(ok=False, errors=exc.messages)

        user.set_password(new_password)
        user.save()

        otp.is_used = True
        otp.save()
        PasswordResetOTP.objects.filter(user=user).update(is_used=True)

        return SimplePayload(ok=True, errors=[])


class UsersMutations(graphene.ObjectType):
    change_password = ChangePasswordMutation.Field()
    request_password_reset = RequestPasswordResetMutation.Field()
    validate_reset_code = ValidateResetCodeMutation.Field()
    confirm_password_reset = ConfirmPasswordResetMutation.Field()
