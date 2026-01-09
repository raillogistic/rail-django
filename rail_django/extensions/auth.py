"""
Authentication system for Django GraphQL Auto-Generation.

This module provides JWT-based authentication with built-in GraphQL mutations
for login, register, token refresh, and user management.
"""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import graphene
import jwt
from django.apps import apps
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from graphene_django import DjangoObjectType

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

from ..security.rbac import role_manager
from ..extensions.permissions import (
    OperationType,
    PermissionInfo,
    permission_manager,
)

logger = logging.getLogger(__name__)

# User model will be retrieved dynamically when needed


def _get_effective_permissions(user: "AbstractUser") -> List[str]:
    """Return a sorted list of effective permissions for a user."""
    if not user:
        return []

    try:
        permissions = role_manager.get_effective_permissions(user)
        return sorted(permissions)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Impossible de récupérer les permissions de %s: %s", user, exc)
        return []


def _build_model_permission_snapshot(user: "AbstractUser") -> List[PermissionInfo]:
    """Return model-level CRUD permissions for a user."""
    if not user or not getattr(user, "is_authenticated", False):
        return []

    permissions: List[PermissionInfo] = []
    for model in apps.get_models():
        model_label = model._meta.label_lower
        permissions.append(
            PermissionInfo(
                model_name=model_label,
                verbose_name=str(model._meta.verbose_name),
                can_create=permission_manager.check_operation_permission(
                    user, model_label, OperationType.CREATE
                ).allowed,
                can_read=permission_manager.check_operation_permission(
                    user, model_label, OperationType.READ
                ).allowed,
                can_update=permission_manager.check_operation_permission(
                    user, model_label, OperationType.UPDATE
                ).allowed,
                can_delete=permission_manager.check_operation_permission(
                    user, model_label, OperationType.DELETE
                ).allowed,
                can_list=permission_manager.check_operation_permission(
                    user, model_label, OperationType.LIST
                ).allowed,
            )
        )

    return permissions


# Lazy cache for UserSettingsType
_user_settings_type = None


def _get_user_settings_type():
    """Lazily resolve UserSettingsType to avoid AppRegistryNotReady."""
    global _user_settings_type
    if _user_settings_type:
        return _user_settings_type

    try:
        from django.apps import apps

        # Check if apps are ready before calling get_model
        if not apps.ready:
            return None

        UserSettingsModel = apps.get_model("users", "UserSettings")

        class UserSettingsType(DjangoObjectType):
            class Meta:
                model = UserSettingsModel
                fields = (
                    "theme",
                    "mode",
                    "layout",
                    "sidebar_collapse_mode",
                    "font_size",
                    "font_family",
                )

        _user_settings_type = UserSettingsType
        return _user_settings_type
    except (LookupError, Exception):
        return None


class DummySettingsType(graphene.ObjectType):
    """Fallback type when UserSettings model is not available."""

    info = graphene.String(description="Placeholder for missing UserSettings model")
    theme = graphene.String(description="Thème de l'interface")
    mode = graphene.String(description="Mode d'affichage")
    layout = graphene.String(description="Disposition de l'interface")
    sidebar_collapse_mode = graphene.String(
        description="Mode de repli de la barre latérale"
    )
    font_size = graphene.String(description="Taille de police")
    font_family = graphene.String(description="Famille de police")


def _get_safe_settings_type():
    """Returns real UserSettingsType or a dummy fallback to prevent Graphene errors."""
    return _get_user_settings_type() or DummySettingsType


def get_authenticated_user_type():
    """Factory function to create the GraphQL type exposed by auth queries."""

    class AuthenticatedUserType(DjangoObjectType):
        """GraphQL type for authenticated user payloads."""

        permissions = graphene.List(
            graphene.String, description="Permissions effectives de l'utilisateur"
        )
        model_permissions = graphene.List(
            PermissionInfo,
            description="Permissions CRUD détaillées par modèle",
        )
        desc = graphene.String(description="Description de l'utilisateur")

        settings = graphene.Field(
            lambda: _get_safe_settings_type(),
            description="Préférences d'interface utilisateur",
        )

        def resolve_desc(self, info):
            return self.get_full_name()

        class Meta:
            model = get_user_model()
            fields = (
                "id",
                "username",
                "email",
                "first_name",
                "last_name",
                "is_staff",
                "is_superuser",
                "is_active",
                "date_joined",
                "last_login",
            )

        def resolve_permissions(self, info):
            return _get_effective_permissions(self)

        def resolve_model_permissions(self, info):
            return _build_model_permission_snapshot(self)

        def resolve_settings(self, info):
            # Only resolve settings if the model and GraphQL type exist
            if not _get_user_settings_type():
                return None

            try:
                return self.settings
            except Exception:
                return None

    return AuthenticatedUserType


class UpdateMySettingsMutation(graphene.Mutation):
    """Mutation to update current user's settings."""

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
        user = info.context.user
        if not user or not user.is_authenticated:
            return UpdateMySettingsMutation(
                ok=False,
                errors=["Vous devez être connecté pour modifier vos paramètres."],
            )

        # Check if settings system is active
        if not _get_user_settings_type():
            return UpdateMySettingsMutation(
                ok=False,
                errors=["Le système de préférences utilisateur n'est pas activé."],
            )

        try:
            from django.apps import apps

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
                f"Erreur lors de la mise à jour des paramètres utilisateur: {e}"
            )
            return UpdateMySettingsMutation(
                ok=False,
                errors=["Erreur interne lors de la mise à jour des paramètres."],
            )


# Create a lazy reference that will be resolved when needed
_authenticated_user_type = None


def UserType():
    """Lazy UserType that resolves the model when Django apps are ready."""
    global _authenticated_user_type
    if _authenticated_user_type is None:
        _authenticated_user_type = get_authenticated_user_type()
    return _authenticated_user_type


class AuthPayload(graphene.ObjectType):
    """Payload returned by authentication mutations."""

    ok = graphene.Boolean(required=True, description="Indique si l'opération a réussi")
    user = graphene.Field(lambda: UserType(), description="Utilisateur authentifié")
    permissions = graphene.List(
        graphene.String,
        description="Liste des permissions effectives disponibles pour l'utilisateur",
    )
    token = graphene.String(description="Token JWT d'authentification")
    refresh_token = graphene.String(description="Token de rafraîchissement")
    expires_at = graphene.DateTime(description="Date d'expiration du token")
    errors = graphene.List(
        graphene.String, required=True, description="Liste des erreurs"
    )


class JWTManager:
    """Gestionnaire des tokens JWT pour l'authentification."""

    @staticmethod
    def get_jwt_secret() -> str:
        """Récupère la clé secrète JWT depuis les paramètres Django."""
        return getattr(settings, "JWT_SECRET_KEY", settings.SECRET_KEY)

    @staticmethod
    def get_jwt_expiration() -> int:
        """Récupère la durée d'expiration du token en secondes.

        Supports non-expiring tokens when configured with 0 or None.
        Accepts either legacy `JWT_EXPIRATION_DELTA` or new
        `JWT_ACCESS_TOKEN_LIFETIME` setting (in seconds).
        """
        # Prefer explicit access token lifetime if present
        lifetime = getattr(settings, "JWT_ACCESS_TOKEN_LIFETIME", None)
        if lifetime is None:
            lifetime = getattr(settings, "JWT_EXPIRATION_DELTA", 3600 * 72)
        # Normalize types that might be timedelta
        if isinstance(lifetime, timedelta):
            lifetime_seconds = int(lifetime.total_seconds())
        else:
            lifetime_seconds = int(lifetime)
        return lifetime_seconds

    @staticmethod
    def get_refresh_expiration() -> int:
        """Récupère la durée d'expiration du refresh token en secondes.

        Accepts either legacy `JWT_REFRESH_EXPIRATION_DELTA` or new
        `JWT_REFRESH_TOKEN_LIFETIME` setting (in seconds).
        """
        lifetime = getattr(settings, "JWT_REFRESH_TOKEN_LIFETIME", None)
        if lifetime is None:
            lifetime = getattr(settings, "JWT_REFRESH_EXPIRATION_DELTA", 86400)
        if isinstance(lifetime, timedelta):
            lifetime_seconds = int(lifetime.total_seconds())
        else:
            lifetime_seconds = int(lifetime)
        return lifetime_seconds

    @classmethod
    def generate_token(cls, user: "AbstractUser") -> Dict[str, Any]:
        """
        Génère un token JWT pour l'utilisateur.

        Args:
            user: Instance de l'utilisateur Django

        Returns:
            Dict contenant le token, refresh_token et expires_at
        """
        now = timezone.now()
        access_lifetime = cls.get_jwt_expiration()
        refresh_lifetime = cls.get_refresh_expiration()
        # If access_lifetime is 0 or negative, treat as non-expiring (no 'exp')
        expiration = (
            None if access_lifetime <= 0 else now + timedelta(seconds=access_lifetime)
        )
        refresh_expiration = now + timedelta(seconds=refresh_lifetime)
        permission_snapshot = _get_effective_permissions(user)

        payload = {
            "user_id": user.id,
            "username": user.username,
            "iat": now,
            "type": "access",
            "permissions": permission_snapshot,
        }
        # Only include 'exp' if token should expire
        if expiration is not None:
            payload["exp"] = expiration

        refresh_payload = {
            "user_id": user.id,
            "exp": refresh_expiration,
            "iat": now,
            "type": "refresh",
        }

        token = jwt.encode(payload, cls.get_jwt_secret(), algorithm="HS256")
        refresh_token = jwt.encode(
            refresh_payload, cls.get_jwt_secret(), algorithm="HS256"
        )

        return {
            "token": token,
            "refresh_token": refresh_token,
            "expires_at": expiration,
            "permissions": permission_snapshot,
        }

    @classmethod
    def verify_token(cls, token: str) -> Optional[Dict[str, Any]]:
        """
        Vérifie et décode un token JWT.

        Args:
            token: Token JWT à vérifier

        Returns:
            Payload décodé ou None si le token est invalide
        """
        try:
            payload = jwt.decode(token, cls.get_jwt_secret(), algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token JWT expiré")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token JWT invalide: {e}")
            return None

    @classmethod
    def refresh_token(cls, refresh_token: str) -> Optional[Dict[str, Any]]:
        """
        Rafraîchit un token d'accès à partir d'un refresh token.

        Args:
            refresh_token: Token de rafraîchissement

        Returns:
            Nouveau token d'accès ou None si le refresh token est invalide
        """
        payload = cls.verify_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None

        try:
            User = get_user_model()
            user = User.objects.get(id=payload["user_id"])
            return cls.generate_token(user)
        except User.DoesNotExist:
            logger.warning(
                f"Utilisateur introuvable pour le refresh token: {payload.get('user_id')}"
            )
            return None


def set_auth_cookies(request, access_token=None, refresh_token=None):
    """Sets secure HttpOnly cookies for authentication tokens."""
    if not hasattr(request, "_set_auth_cookies"):
        request._set_auth_cookies = []

    # Force secure=False in DEBUG mode to allow cookies on localhost HTTP
    secure = getattr(settings, "SESSION_COOKIE_SECURE", False)
    if getattr(settings, "DEBUG", False):
        secure = False

    samesite = "Lax"

    if access_token:
        request._set_auth_cookies.append(
            {
                "key": getattr(settings, "JWT_AUTH_COOKIE", "jwt"),
                "value": access_token,
                "httponly": True,
                "secure": secure,
                "samesite": samesite,
                "max_age": getattr(settings, "JWT_ACCESS_TOKEN_LIFETIME", 3600),
            }
        )

    if refresh_token:
        request._set_auth_cookies.append(
            {
                "key": getattr(settings, "JWT_REFRESH_COOKIE", "refresh_token"),
                "value": refresh_token,
                "httponly": True,
                "secure": secure,
                "samesite": samesite,
                "max_age": getattr(settings, "JWT_REFRESH_TOKEN_LIFETIME", 86400 * 7),
                "path": "/",
            }
        )


def delete_auth_cookies(request):
    """Marks authentication cookies for deletion."""
    if not hasattr(request, "_delete_auth_cookies"):
        request._delete_auth_cookies = []

    request._delete_auth_cookies.append(getattr(settings, "JWT_AUTH_COOKIE", "jwt"))
    request._delete_auth_cookies.append(
        getattr(settings, "JWT_REFRESH_COOKIE", "refresh_token")
    )


class LoginMutation(graphene.Mutation):
    """Mutation de connexion utilisateur."""

    class Arguments:
        username = graphene.String(required=True, description="Nom d'utilisateur")
        password = graphene.String(required=True, description="Mot de passe")

    Output = AuthPayload

    def mutate(self, info, username: str, password: str):
        """
        Authentifie un utilisateur et retourne un token JWT.

        Args:
            username: Nom d'utilisateur
            password: Mot de passe

        Returns:
            AuthPayload avec le token et les informations utilisateur
        """
        try:
            # Authentification de l'utilisateur
            user = authenticate(username=username, password=password)

            if not user:
                return AuthPayload(
                    ok=False, errors=["Nom d'utilisateur ou mot de passe incorrect"]
                )

            if not user.is_active:
                return AuthPayload(ok=False, errors=["Compte utilisateur désactivé"])

            # Génération du token JWT
            token_data = JWTManager.generate_token(user)
            permissions = token_data.get("permissions", [])

            # Mise à jour de la dernière connexion
            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])

            logger.info(f"Connexion réussie pour l'utilisateur: {username}")

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
    """Mutation d'inscription utilisateur."""

    class Arguments:
        username = graphene.String(required=True, description="Nom d'utilisateur")
        email = graphene.String(required=True, description="Adresse email")
        password = graphene.String(required=True, description="Mot de passe")
        first_name = graphene.String(description="Prénom")
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
        Crée un nouvel utilisateur et retourne un token JWT.

        Args:
            username: Nom d'utilisateur
            email: Adresse email
            password: Mot de passe
            first_name: Prénom (optionnel)
            last_name: Nom de famille (optionnel)

        Returns:
            AuthPayload avec le token et les informations utilisateur
        """
        try:
            # Get the User model dynamically
            User = get_user_model()

            # Validation des données
            errors = []

            # Vérification de l'unicité du nom d'utilisateur
            if User.objects.filter(username=username).exists():
                errors.append("Ce nom d'utilisateur est déjà utilisé")

            # Vérification de l'unicité de l'email
            if User.objects.filter(email=email).exists():
                errors.append("Cette adresse email est déjà utilisée")

            # Validation du mot de passe
            try:
                validate_password(password)
            except ValidationError as e:
                errors.extend(e.messages)

            if errors:
                return AuthPayload(ok=False, errors=errors)

            # Création de l'utilisateur
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )

            # Génération du token JWT
            token_data = JWTManager.generate_token(user)
            permissions = token_data.get("permissions", [])

            logger.info(f"Inscription réussie pour l'utilisateur: {username}")

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
    """Mutation de rafraîchissement de token."""

    class Arguments:
        refresh_token = graphene.String(
            required=False,
            description="Token de rafraîchissement (optionnel si cookie présent)",
        )

    Output = AuthPayload

    def mutate(self, info, refresh_token: str = None):
        """
        Rafraîchit un token d'accès.

        Args:
            refresh_token: Token de rafraîchissement

        Returns:
            AuthPayload avec le nouveau token
        """
        try:
            # Try to get refresh token from cookie if not provided
            if not refresh_token:
                cookie_name = getattr(settings, "JWT_REFRESH_COOKIE", "refresh_token")
                refresh_token = info.context.COOKIES.get(cookie_name)

            if not refresh_token:
                return AuthPayload(
                    ok=False, errors=["Token de rafraîchissement manquant"]
                )

            token_data = JWTManager.refresh_token(refresh_token)

            if not token_data:
                return AuthPayload(
                    ok=False, errors=["Token de rafraîchissement invalide ou expiré"]
                )

            # Récupération de l'utilisateur pour le retourner
            payload = JWTManager.verify_token(token_data["token"])
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
            logger.error(f"Erreur lors du rafraîchissement du token: {e}")
            return AuthPayload(
                ok=False, errors=["Erreur interne lors du rafraîchissement du token"]
            )


class LogoutMutation(graphene.Mutation):
    """Mutation de déconnexion utilisateur."""

    class Arguments:
        pass  # Pas d'arguments nécessaires, on utilise le token dans le contexte

    ok = graphene.Boolean(required=True)
    errors = graphene.List(graphene.String, required=True)

    def mutate(self, info):
        """
        Déconnecte l'utilisateur (côté client principalement).

        Note: Avec JWT, la déconnexion est principalement côté client.
        Cette mutation peut être étendue pour maintenir une blacklist de tokens.
        """
        try:
            # Clear cookies
            delete_auth_cookies(info.context)

            # Pour l'instant, on retourne simplement un succès
            # Dans une implémentation plus avancée, on pourrait :
            # - Ajouter le token à une blacklist
            # - Invalider tous les tokens de l'utilisateur
            # - Logger la déconnexion

            return LogoutMutation(ok=True, errors=[])

        except Exception as e:
            logger.error(f"Erreur lors de la déconnexion: {e}")
            return LogoutMutation(
                ok=False, errors=["Erreur interne lors de la déconnexion"]
            )


class MeQuery(graphene.ObjectType):
    """Query pour récupérer les informations de l'utilisateur connecté."""

    me = graphene.Field(
        lambda: UserType(), description="Informations de l'utilisateur connecté"
    )
    # xx = graphene.String()

    def resolve_me(self, info):
        """
        Retourne les informations de l'utilisateur connecté.

        Returns:
            User instance ou None si non authentifié
        """
        # Try the user injected in the request/context first
        user = getattr(info.context, "user", None)

        if user and getattr(user, "is_authenticated", False):
            return user

        # Fallback: authenticate via JWT from Authorization header
        try:
            from .auth import authenticate_request

            user_from_jwt = authenticate_request(info)
            if user_from_jwt and getattr(user_from_jwt, "is_authenticated", False):
                return user_from_jwt
        except Exception:
            # Silently ignore and return None if auth fails
            pass
        return None


class AuthMutations(graphene.ObjectType):
    """Mutations d'authentification disponibles."""

    login = LoginMutation.Field(description="Connexion utilisateur")
    # register = RegisterMutation.Field(description="Inscription utilisateur")
    refresh_token = RefreshTokenMutation.Field(description="Rafraîchissement du token")
    logout = LogoutMutation.Field(description="Déconnexion utilisateur")


def get_user_from_token(token: str) -> Optional["AbstractUser"]:
    """
    Récupère un utilisateur à partir d'un token JWT.

    Args:
        token: Token JWT

    Returns:
        Instance User ou None si le token est invalide
    """
    payload = JWTManager.verify_token(token)
    if not payload:
        return None

    try:
        User = get_user_model()
        return User.objects.get(id=payload["user_id"])
    except User.DoesNotExist:
        return None


def authenticate_request(info) -> Optional["AbstractUser"]:
    """
    Authentifie une requête GraphQL à partir du token dans les headers.

    Args:
        info: Contexte GraphQL

    Returns:
        Instance User ou None si non authentifié
    """
    request = info.context

    # Récupération du token depuis les headers
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]
    return get_user_from_token(token)
