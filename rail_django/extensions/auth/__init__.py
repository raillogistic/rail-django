"""
Authentication extension for Django GraphQL Auto-Generation.

This package provides JWT-based authentication with built-in GraphQL mutations
for login, register, token refresh, and user management.

Example usage:
    from rail_django.extensions.auth import (
        JWTManager,
        LoginMutation,
        MeQuery,
        AuthMutations,
        authenticate_request,
    )

    # Generate a token for a user
    token_data = JWTManager.generate_token(user)

    # Verify a token
    payload = JWTManager.verify_token(token)

    # Use in GraphQL schema
    class Query(MeQuery, graphene.ObjectType):
        pass

    class Mutation(AuthMutations, graphene.ObjectType):
        pass

    schema = graphene.Schema(query=Query, mutation=Mutation)
"""

# JWT Management
from .jwt import (
    JWTManager,
    RefreshTokenStore,
    get_refresh_token_store,
)

# GraphQL Mutations
from .mutations import (
    LoginMutation,
    RegisterMutation,
    RefreshTokenMutation,
    LogoutMutation,
    UpdateMySettingsMutation,
    VerifyMFALoginMutation,
    RevokeSessionMutation,
    RevokeAllSessionsMutation,
    AuthMutations,
)

# GraphQL Queries and Types
from .queries import (
    MeQuery,
    UserType,
    AuthPayload,
    get_authenticated_user_type,
    DummySettingsType,
)

# Cookie Handling
from .cookies import (
    set_auth_cookies,
    delete_auth_cookies,
)

# Utility Functions
from .utils import (
    get_user_from_token,
    authenticate_request,
)

# Internal utilities (exported for backwards compatibility)
from .utils import (
    _get_effective_permissions,
    _build_model_permission_snapshot,
)

from .cookies import _resolve_cookie_policy

from .queries import (
    _get_user_settings_type,
    _get_safe_settings_type,
)

__all__ = [
    # JWT Management
    "JWTManager",
    "RefreshTokenStore",
    "get_refresh_token_store",
    # GraphQL Mutations
    "LoginMutation",
    "RegisterMutation",
    "RefreshTokenMutation",
    "LogoutMutation",
    "UpdateMySettingsMutation",
    "VerifyMFALoginMutation",
    "RevokeSessionMutation",
    "RevokeAllSessionsMutation",
    "AuthMutations",
    # GraphQL Queries and Types
    "MeQuery",
    "UserType",
    "AuthPayload",
    "get_authenticated_user_type",
    "DummySettingsType",
    # Cookie Handling
    "set_auth_cookies",
    "delete_auth_cookies",
    # Utility Functions
    "get_user_from_token",
    "authenticate_request",
]
