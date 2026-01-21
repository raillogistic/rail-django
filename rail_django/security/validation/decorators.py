"""
Validation decorators for GraphQL resolvers.

This module provides decorators for automatic input validation
in GraphQL mutation resolvers.
"""

from typing import Callable, Optional

from .sanitizer import GraphQLInputSanitizer


def validate_input(validator_func: Optional[Callable] = None) -> Callable:
    """Decorator to validate GraphQL resolver inputs.

    This decorator automatically sanitizes input arguments named 'input',
    'data', or ending with '_data' before passing them to the resolver.

    Args:
        validator_func: Optional custom validation function to run after
            sanitization. It receives the same (*args, **kwargs) as the
            decorated function and can raise exceptions to block execution.

    Returns:
        A decorator function.

    Example:
        @validate_input()
        def resolve_create_user(root, info, input):
            # input is already sanitized here
            return User.objects.create(**input)

        @validate_input(custom_validator)
        def resolve_update_user(root, info, input):
            # custom_validator(root, info, input=input) is called first
            return User.objects.filter(id=input['id']).update(**input)

    Note:
        The decorator looks for these argument names:
        - 'input': Standard GraphQL input argument
        - 'data': Alternative input argument name
        - '*_data': Any argument ending with '_data'
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            sanitizer = GraphQLInputSanitizer()

            # Find and sanitize input-like arguments
            input_keys = [
                key
                for key in kwargs
                if key == "input" or key == "data" or key.endswith("_data")
            ]

            for key in input_keys:
                kwargs[key] = sanitizer.sanitize_mutation_input(kwargs[key])

            # Run custom validator if provided
            if validator_func:
                validator_func(*args, **kwargs)

            return func(*args, **kwargs)

        # Preserve function metadata
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__module__ = func.__module__
        if hasattr(func, "__annotations__"):
            wrapper.__annotations__ = func.__annotations__
        if hasattr(func, "__dict__"):
            wrapper.__dict__.update(func.__dict__)

        return wrapper

    return decorator
