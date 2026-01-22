"""
GraphQL security decorators.
"""

from functools import wraps
from graphql import GraphQLError
from .config import SecurityConfig


def require_introspection_permission(func):
    """
    Décorateur pour protéger les champs d'introspection.

    Args:
        func: Fonction à protéger

    Returns:
        Fonction décorée
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Extraire le contexte GraphQL
        info = None
        for arg in args:
            if hasattr(arg, 'context'):
                info = arg
                break

        if not info:
            raise GraphQLError("Contexte GraphQL non disponible")

        user = getattr(info.context, 'user', None)
        if not user or not user.is_authenticated:
            raise GraphQLError("Authentification requise pour l'introspection")

        # Vérifier les permissions d'introspection
        config = getattr(info.context, 'security_config', SecurityConfig())
        if not config.enable_introspection:
            from ..rbac import role_manager
            user_roles = role_manager.get_user_roles(user)
            if not any(role in config.introspection_roles for role in user_roles):
                raise GraphQLError("Permission d'introspection requise")

        return func(*args, **kwargs)

    return wrapper
