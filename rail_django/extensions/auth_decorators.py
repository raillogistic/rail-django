"""
JWT Authentication decorators for Django views.

This module provides decorators to protect Django views with JWT token authentication,
similar to the authentication used in GraphQL schemas.
"""

import logging
from functools import wraps
from typing import Any, Callable, Dict, Optional

from django.contrib.auth import get_user_model
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .auth import JWTManager

logger = logging.getLogger(__name__)


def jwt_required(view_func: Callable) -> Callable:
    """
    Decorator that requires JWT authentication for a Django view.

    This decorator validates JWT tokens in the Authorization header and
    injects the authenticated user into the request object.

    Usage:
        @jwt_required
        def my_protected_view(request):
            # request.user will contain the authenticated user
            return JsonResponse({'message': 'Success'})

    Args:
        view_func: The view function to protect

    Returns:
        Wrapped view function with JWT authentication
    """
    @wraps(view_func)
    @csrf_exempt
    def wrapper(request: HttpRequest, *args, **kwargs):
        # Extract token from Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        if not auth_header:
            return JsonResponse({
                'error': 'Authentication required',
                'message': 'Authorization header is missing'
            }, status=401)

        # Validate header format
        if not (auth_header.startswith('Bearer ') or auth_header.startswith('Token ')):
            return JsonResponse({
                'error': 'Invalid authentication format',
                'message': 'Authorization header must start with "Bearer " or "Token "'
            }, status=401)

        # Extract token
        try:
            token = auth_header.split(' ')[1]
        except IndexError:
            return JsonResponse({
                'error': 'Invalid token format',
                'message': 'Token is missing from Authorization header'
            }, status=401)

        # Verify JWT token
        payload = JWTManager.verify_token(token)
        if not payload:
            return JsonResponse({
                'error': 'Invalid or expired token',
                'message': 'JWT token validation failed'
            }, status=401)

        # Get user from token payload
        user_id = payload.get('user_id')
        if not user_id:
            return JsonResponse({
                'error': 'Invalid token payload',
                'message': 'User ID not found in token'
            }, status=401)

        # Validate user exists and is active
        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
            if not user.is_active:
                return JsonResponse({
                    'error': 'Account disabled',
                    'message': 'User account is not active'
                }, status=401)
        except User.DoesNotExist:
            return JsonResponse({
                'error': 'User not found',
                'message': 'User associated with token does not exist'
            }, status=401)

        # Inject user into request
        request.user = user
        request.jwt_payload = payload

        # Log successful authentication
        logger.info(f"JWT authentication successful for user {user.username} (ID: {user.id})")

        # Call the original view
        return view_func(request, *args, **kwargs)

    return wrapper


def jwt_optional(view_func: Callable) -> Callable:
    """
    Decorator that optionally validates JWT authentication for a Django view.

    If a valid JWT token is provided, the user will be injected into the request.
    If no token or an invalid token is provided, the view will still execute
    but request.user will be AnonymousUser.

    Usage:
        @jwt_optional
        def my_view(request):
            if request.user.is_authenticated:
                # User is authenticated via JWT
                pass
            else:
                # Anonymous user
                pass
            return JsonResponse({'message': 'Success'})

    Args:
        view_func: The view function to optionally protect

    Returns:
        Wrapped view function with optional JWT authentication
    """
    @wraps(view_func)
    @csrf_exempt
    def wrapper(request: HttpRequest, *args, **kwargs):
        # Extract token from Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        if auth_header and (auth_header.startswith('Bearer ') or auth_header.startswith('Token ')):
            try:
                token = auth_header.split(' ')[1]
                payload = JWTManager.verify_token(token)

                if payload:
                    user_id = payload.get('user_id')
                    if user_id:
                        User = get_user_model()
                        try:
                            user = User.objects.get(id=user_id)
                            if user.is_active:
                                request.user = user
                                request.jwt_payload = payload
                                logger.info(
                                    f"Optional JWT authentication successful for user {user.username}")
                        except User.DoesNotExist:
                            pass
            except (IndexError, Exception) as e:
                logger.warning(f"Optional JWT authentication failed: {e}")

        # Call the original view (with or without authenticated user)
        return view_func(request, *args, **kwargs)

    return wrapper


def get_user_from_jwt(request: HttpRequest) -> Optional[Dict[str, Any]]:
    """
    Extract user information from JWT token in request.

    This is a utility function that can be used in views to manually
    extract user information from JWT tokens without using decorators.

    Args:
        request: Django HTTP request object

    Returns:
        Dictionary with user information or None if authentication fails
    """
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')

    if not auth_header or not (auth_header.startswith('Bearer ') or auth_header.startswith('Token ')):
        return None

    try:
        token = auth_header.split(' ')[1]
        payload = JWTManager.verify_token(token)

        if not payload:
            return None

        user_id = payload.get('user_id')
        if not user_id:
            return None

        User = get_user_model()
        user = User.objects.get(id=user_id)

        if not user.is_active:
            return None

        return {
            'user': user,
            'payload': payload
        }

    except (IndexError, User.DoesNotExist, Exception):
        return None


def require_permissions(*permissions: str):
    """
    Decorator that requires specific permissions in addition to JWT authentication.

    This decorator first validates JWT authentication, then checks if the user
    has the required permissions.

    Usage:
        @require_permissions('blog.add_post', 'blog.change_post')
        def create_post_view(request):
            return JsonResponse({'message': 'Post created'})

    Args:
        permissions: List of permission strings to check

    Returns:
        Decorator function
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @jwt_required
        def wrapper(request: HttpRequest, *args, **kwargs):
            # Check if user has required permissions
            missing_permissions = []
            for permission in permissions:
                if not request.user.has_perm(permission):
                    missing_permissions.append(permission)

            if missing_permissions:
                return JsonResponse({
                    'error': 'Insufficient permissions',
                    'message': f'Missing permissions: {", ".join(missing_permissions)}'
                }, status=403)

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator
