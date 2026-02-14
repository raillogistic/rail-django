"""
GraphQL queries for authentication.

This module provides GraphQL types and queries for retrieving
authenticated user information.
"""

import logging
from typing import TYPE_CHECKING

import graphene
from django.contrib.auth import get_user_model
from graphene_django import DjangoObjectType

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

from ...extensions.permissions import PermissionInfo
from .utils import (
    _get_effective_permissions,
    _build_model_permission_snapshot,
    _get_user_roles_detail,
)

logger = logging.getLogger(__name__)


# Lazy cache for UserSettingsType
_user_settings_type = None


def _get_user_settings_type():
    """
    Lazily resolve UserSettingsType to avoid AppRegistryNotReady.

    This function dynamically creates a GraphQL type for user settings
    only when needed and after Django apps are fully initialized.

    Returns:
        The UserSettingsType class or None if the model is not available.
    """
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
    """
    Fallback type when UserSettings model is not available.

    This type provides placeholder fields that match the expected
    UserSettings interface, allowing the schema to be valid even
    when the UserSettings model is not defined.
    """

    info = graphene.String(description="Placeholder for missing UserSettings model")
    theme = graphene.String(description="Theme de l'interface")
    mode = graphene.String(description="Mode d'affichage")
    layout = graphene.String(description="Disposition de l'interface")
    sidebar_collapse_mode = graphene.String(
        description="Mode de repli de la barre laterale"
    )
    font_size = graphene.String(description="Taille de police")
    font_family = graphene.String(description="Famille de police")


class AuthPermissionType(graphene.ObjectType):
    """Permission details for auth payloads."""

    id = graphene.ID()
    name = graphene.String()
    codename = graphene.String()


class AuthRoleType(graphene.ObjectType):
    """Role details for auth payloads."""

    id = graphene.ID()
    name = graphene.String()
    permissions = graphene.List(AuthPermissionType)


def _get_safe_settings_type():
    """
    Return real UserSettingsType or a dummy fallback.

    This prevents Graphene errors when the UserSettings model
    is not available in the application.

    Returns:
        UserSettingsType if available, otherwise DummySettingsType.
    """
    return _get_user_settings_type() or DummySettingsType


def get_authenticated_user_type():
    """
    Factory function to create the GraphQL type exposed by auth queries.

    This function creates a DjangoObjectType for the authenticated user
    with additional fields for permissions and settings.

    Returns:
        The AuthenticatedUserType class.

    Example:
        UserType = get_authenticated_user_type()
        # Use UserType in your GraphQL schema
    """

    class AuthenticatedUserType(DjangoObjectType):
        """GraphQL type for authenticated user payloads."""

        permissions = graphene.List(
            graphene.String, description="Permissions effectives de l'utilisateur"
        )
        roles = graphene.List(
            AuthRoleType,
            description="Roles RBAC et groupes Django de l'utilisateur",
        )
        model_permissions = graphene.List(
            PermissionInfo,
            description="Permissions CRUD detaillees par modele",
        )
        desc = graphene.String(description="Description de l'utilisateur")

        settings = graphene.Field(
            lambda: _get_safe_settings_type(),
            description="Preferences d'interface utilisateur",
        )

        def resolve_desc(self, info):
            """Resolve the user description (full name)."""
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
            """Resolve the user's effective permissions."""
            return _get_effective_permissions(self)

        def resolve_roles(self, info):
            """Resolve the user's RBAC roles and Django groups."""
            return _get_user_roles_detail(self)

        def resolve_model_permissions(self, info):
            """Resolve the user's model-level CRUD permissions."""
            return _build_model_permission_snapshot(self)

        def resolve_settings(self, info):
            """Resolve the user's settings preferences."""
            # Only resolve settings if the model and GraphQL type exist
            if not _get_user_settings_type():
                return None

            try:
                return self.settings
            except Exception:
                return None

    return AuthenticatedUserType


# Create a lazy reference that will be resolved when needed
_authenticated_user_type = None


def UserType():
    """
    Lazy UserType that resolves the model when Django apps are ready.

    This function returns a cached AuthenticatedUserType, creating it
    on first access to avoid issues with Django's app registry.

    Returns:
        The AuthenticatedUserType class.
    """
    global _authenticated_user_type
    if _authenticated_user_type is None:
        _authenticated_user_type = get_authenticated_user_type()
    return _authenticated_user_type


class AuthPayload(graphene.ObjectType):
    """
    Payload returned by authentication mutations.

    This type represents the response from login, register, and
    token refresh operations.

    Attributes:
        ok: Indicates if the operation was successful.
        user: The authenticated user (if successful).
        permissions: List of effective permissions for the user.
        token: The JWT access token.
        refresh_token: The JWT refresh token.
        expires_at: When the access token expires.
        errors: List of error messages (if unsuccessful).
    """

    ok = graphene.Boolean(required=True, description="Indique si l'operation a reussi")
    user = graphene.Field(lambda: UserType(), description="Utilisateur authentifie")
    permissions = graphene.List(
        graphene.String,
        description="Liste des permissions effectives disponibles pour l'utilisateur",
    )
    mfa_required = graphene.Boolean(
        description="Indique si l'authentification MFA est requise"
    )
    mfa_setup_required = graphene.Boolean(
        description="Indique si la configuration MFA est requise (pas d'appareil actif)"
    )
    ephemeral_token = graphene.String(
        description="Token ephemere pour la validation MFA"
    )
    token = graphene.String(description="Token JWT d'authentification")
    refresh_token = graphene.String(description="Token de rafraichissement")
    expires_at = graphene.DateTime(description="Date d'expiration du token")
    errors = graphene.List(
        graphene.String, required=True, description="Liste des erreurs"
    )


class MeQuery(graphene.ObjectType):
    """
    Query for retrieving information about the connected user.

    This query type provides a 'me' field that returns the currently
    authenticated user's information.

    Example:
        query {
            me {
                id
                username
                email
                permissions
            }
        }
    """

    me = graphene.Field(
        lambda: UserType(), description="Informations de l'utilisateur connecte"
    )
    viewer = graphene.Field(
        lambda: UserType(),
        description="Alias de `me` pour les tests d'integration",
    )

    def resolve_me(self, info):
        """
        Return information about the connected user.

        This resolver first checks for a user attached to the request
        context, then falls back to JWT authentication from the
        Authorization header.

        Returns:
            The User instance or None if not authenticated.
        """
        # Try the user injected in the request/context first
        user = getattr(info.context, "user", None)

        if user and getattr(user, "is_authenticated", False):
            return user

        # Fallback: authenticate via JWT from Authorization header
        try:
            from .utils import authenticate_request

            user_from_jwt = authenticate_request(info)
            if user_from_jwt and getattr(user_from_jwt, "is_authenticated", False):
                return user_from_jwt
        except Exception:
            # Silently ignore and return None if auth fails
            pass
        return None

    def resolve_viewer(self, info):
        """Return the authenticated user through a stable integration-test alias."""
        return self.resolve_me(info)
