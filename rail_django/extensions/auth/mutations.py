"""
GraphQL mutations for authentication.

This module provides GraphQL mutations for user authentication operations
including login, registration, token refresh, and logout.
"""

import logging

import graphene
from django.apps import apps
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from .cookies import set_auth_cookies, delete_auth_cookies
from .jwt import JWTManager
from .queries import (
    AuthPayload,
    _get_user_settings_type,
    _get_safe_settings_type,
)
from .utils import _get_effective_permissions

logger = logging.getLogger(__name__)


class UpdateMySettingsMutation(graphene.Mutation):
    """
    Mutation to update the current user's settings.

    This mutation allows authenticated users to update their
    interface preferences such as theme, layout, and font settings.

    Example:
        mutation {
            updateMySettings(theme: "dark", fontSize: "large") {
                ok
                errors
                settings {
                    theme
                    fontSize
                }
            }
        }
    """

    class Arguments:
        theme = graphene.String()
        mode = graphene.String()
        layout = graphene.String()
        sidebar_collapse_mode = graphene.String()
        font_size = graphene.String()
        font_family = graphene.String()

    ok = graphene.Boolean(required=True)
    errors = graphene.List(graphene.String, required=True)

    # Use lambda with fallback for lazy resolution
    settings = graphene.Field(lambda: _get_safe_settings_type())

    def mutate(self, info, **kwargs):
        """
        Update the current user's settings.

        Args:
            info: GraphQL resolve info.
            **kwargs: Setting fields to update.

        Returns:
            UpdateMySettingsMutation with success status and updated settings.
        """
        user = info.context.user
        if not user or not user.is_authenticated:
            return UpdateMySettingsMutation(
                ok=False,
                errors=["Vous devez etre connecte pour modifier vos parametres."],
            )

        # Check if settings system is active
        if not _get_user_settings_type():
            return UpdateMySettingsMutation(
                ok=False,
                errors=["Le systeme de preferences utilisateur n'est pas active."],
            )

        try:
            UserSettingsModel = apps.get_model("users", "UserSettings")

            # Get or create settings
            settings_obj, created = UserSettingsModel.objects.get_or_create(user=user)

            # Update fields
            for field, value in kwargs.items():
                if value is not None and hasattr(settings_obj, field):
                    setattr(settings_obj, field, value)

            settings_obj.save()

            return UpdateMySettingsMutation(ok=True, errors=[], settings=settings_obj)

        except Exception as e:
            logger.error(
                f"Erreur lors de la mise a jour des parametres utilisateur: {e}"
            )
            return UpdateMySettingsMutation(
                ok=False,
                errors=["Erreur interne lors de la mise a jour des parametres."],
            )


class LoginMutation(graphene.Mutation):
    """
    Mutation for user login.

    This mutation authenticates a user with username and password,
    generates JWT tokens, and sets authentication cookies.

    Example:
        mutation {
            login(username: "john", password: "secret") {
                ok
                token
                refreshToken
                user {
                    id
                    username
                }
                errors
            }
        }
    """

    class Arguments:
        username = graphene.String(required=True, description="Nom d'utilisateur")
        password = graphene.String(required=True, description="Mot de passe")

    Output = AuthPayload

    def mutate(self, info, username: str, password: str):
        """
        Authenticate a user and return a JWT token.

        Args:
            info: GraphQL resolve info.
            username: The username to authenticate.
            password: The password to verify.

        Returns:
            AuthPayload with token and user information.
        """
        try:
            # Authenticate the user
            user = authenticate(username=username, password=password)

            if not user:
                return AuthPayload(
                    ok=False, errors=["Nom d'utilisateur ou mot de passe incorrect"]
                )

            if not user.is_active:
                return AuthPayload(ok=False, errors=["Compte utilisateur desactive"])

            # Generate JWT token
            token_data = JWTManager.generate_token(user)
            permissions = token_data.get("permissions", [])

            # Update last login
            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])

            logger.info(f"Connexion reussie pour l'utilisateur: {username}")

            # Set HttpOnly cookies
            set_auth_cookies(
                info.context,
                access_token=token_data["token"],
                refresh_token=token_data["refresh_token"],
            )

            return AuthPayload(
                ok=True,
                user=user,
                token=token_data["token"],
                refresh_token=token_data["refresh_token"],
                expires_at=token_data["expires_at"],
                permissions=permissions,
                errors=[],
            )

        except Exception as e:
            logger.error(f"Erreur lors de la connexion: {e}")
            return AuthPayload(ok=False, errors=["Erreur interne lors de la connexion"])


class RegisterMutation(graphene.Mutation):
    """
    Mutation for user registration.

    This mutation creates a new user account with the provided
    credentials and profile information.

    Example:
        mutation {
            register(
                username: "newuser",
                email: "user@example.com",
                password: "SecurePass123!"
            ) {
                ok
                token
                user {
                    id
                    username
                }
                errors
            }
        }
    """

    class Arguments:
        username = graphene.String(required=True, description="Nom d'utilisateur")
        email = graphene.String(required=True, description="Adresse email")
        password = graphene.String(required=True, description="Mot de passe")
        first_name = graphene.String(description="Prenom")
        last_name = graphene.String(description="Nom de famille")

    Output = AuthPayload

    def mutate(
        self,
        info,
        username: str,
        email: str,
        password: str,
        first_name: str = "",
        last_name: str = "",
    ):
        """
        Create a new user and return a JWT token.

        Args:
            info: GraphQL resolve info.
            username: The desired username.
            email: The user's email address.
            password: The desired password.
            first_name: Optional first name.
            last_name: Optional last name.

        Returns:
            AuthPayload with token and user information.
        """
        try:
            # Get the User model dynamically
            User = get_user_model()

            # Data validation
            errors = []

            # Check username uniqueness
            if User.objects.filter(username=username).exists():
                errors.append("Ce nom d'utilisateur est deja utilise")

            # Check email uniqueness
            if User.objects.filter(email=email).exists():
                errors.append("Cette adresse email est deja utilisee")

            # Validate password
            try:
                validate_password(password)
            except ValidationError as e:
                errors.extend(e.messages)

            if errors:
                return AuthPayload(ok=False, errors=errors)

            # Create user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )

            # Generate JWT token
            token_data = JWTManager.generate_token(user)
            permissions = token_data.get("permissions", [])

            logger.info(f"Inscription reussie pour l'utilisateur: {username}")

            # Set HttpOnly cookies
            set_auth_cookies(
                info.context,
                access_token=token_data["token"],
                refresh_token=token_data["refresh_token"],
            )

            return AuthPayload(
                ok=True,
                user=user,
                token=token_data["token"],
                refresh_token=token_data["refresh_token"],
                expires_at=token_data["expires_at"],
                permissions=permissions,
                errors=[],
            )

        except Exception as e:
            logger.error(f"Erreur lors de l'inscription: {e}")
            return AuthPayload(
                ok=False, errors=["Erreur interne lors de l'inscription"]
            )


class RefreshTokenMutation(graphene.Mutation):
    """
    Mutation for refreshing authentication tokens.

    This mutation uses a refresh token to obtain a new access token,
    optionally rotating the refresh token as well.

    Example:
        mutation {
            refreshToken(refreshToken: "...") {
                ok
                token
                refreshToken
                errors
            }
        }
    """

    class Arguments:
        refresh_token = graphene.String(
            required=False,
            description="Token de rafraichissement (optionnel si cookie present)",
        )

    Output = AuthPayload

    def mutate(self, info, refresh_token: str = None):
        """
        Refresh an access token.

        Args:
            info: GraphQL resolve info.
            refresh_token: The refresh token (optional if cookie is present).

        Returns:
            AuthPayload with new token.
        """
        try:
            # Try to get refresh token from cookie if not provided
            if not refresh_token:
                cookie_name = getattr(settings, "JWT_REFRESH_COOKIE", "refresh_token")
                refresh_token = info.context.COOKIES.get(cookie_name)

            if not refresh_token:
                return AuthPayload(
                    ok=False, errors=["Token de rafraichissement manquant"]
                )

            token_data = JWTManager.refresh_token(refresh_token)

            if not token_data:
                return AuthPayload(
                    ok=False, errors=["Token de rafraichissement invalide ou expire"]
                )

            # Get user to return in response
            payload = JWTManager.verify_token(
                token_data["token"], expected_type="access"
            )
            User = get_user_model()
            user = User.objects.get(id=payload["user_id"])
            permissions = token_data.get(
                "permissions", []
            ) or _get_effective_permissions(user)

            # Set new HttpOnly cookies
            set_auth_cookies(
                info.context,
                access_token=token_data["token"],
                refresh_token=token_data["refresh_token"],
            )

            return AuthPayload(
                ok=True,
                user=user,
                token=token_data["token"],
                refresh_token=token_data["refresh_token"],
                expires_at=token_data["expires_at"],
                permissions=permissions,
                errors=[],
            )

        except Exception as e:
            logger.error(f"Erreur lors du rafraichissement du token: {e}")
            return AuthPayload(
                ok=False, errors=["Erreur interne lors du rafraichissement du token"]
            )


class LogoutMutation(graphene.Mutation):
    """
    Mutation for user logout.

    This mutation clears authentication cookies and invalidates
    the current session.

    Example:
        mutation {
            logout {
                ok
                errors
            }
        }
    """

    class Arguments:
        pass  # No arguments needed, token is in context

    ok = graphene.Boolean(required=True)
    errors = graphene.List(graphene.String, required=True)

    def mutate(self, info):
        """
        Log out the user.

        Note: With JWT, logout is primarily client-side.
        This mutation clears cookies and can be extended to maintain
        a token blacklist.

        Args:
            info: GraphQL resolve info.

        Returns:
            LogoutMutation with success status.
        """
        try:
            # Clear cookies
            delete_auth_cookies(info.context)

            # For now, return success
            # In a more advanced implementation, we could:
            # - Add the token to a blacklist
            # - Invalidate all user tokens
            # - Log the logout

            return LogoutMutation(ok=True, errors=[])

        except Exception as e:
            logger.error(f"Erreur lors de la deconnexion: {e}")
            return LogoutMutation(
                ok=False, errors=["Erreur interne lors de la deconnexion"]
            )


class AuthMutations(graphene.ObjectType):
    """
    Collection of authentication mutations.

    This ObjectType groups all authentication-related mutations
    for easy inclusion in GraphQL schemas.

    Example:
        class Mutation(AuthMutations, graphene.ObjectType):
            pass

        schema = graphene.Schema(mutation=Mutation)
    """

    login = LoginMutation.Field(description="Connexion utilisateur")
    # register = RegisterMutation.Field(description="Inscription utilisateur")
    refresh_token = RefreshTokenMutation.Field(description="Rafraichissement du token")
    logout = LogoutMutation.Field(description="Deconnexion utilisateur")
