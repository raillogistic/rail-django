"""
Decorators for enhancing Django model methods with GraphQL mutation capabilities
and schema registration.
"""

import logging
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Type

import graphene

logger = logging.getLogger(__name__)


def mutation(
    input_type: Optional[Type[graphene.InputObjectType]] = None,
    output_type: Optional[Type[graphene.ObjectType]] = None,
    description: Optional[str] = None,
):
    """
    Decorator to mark a model method as a GraphQL mutation.

    Args:
        input_type: Custom input type for the mutation
        output_type: Custom output type for the mutation
        description: Description for the mutation

    Example:
        @mutation(description="Activate user account")
        def activate_account(self, reason: str = "Manual activation"):
            self.is_active = True
            self.activation_reason = reason
            self.save()
            return True
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Mark the function as a mutation
        wrapper._is_mutation = True
        wrapper._mutation_input_type = input_type
        wrapper._mutation_output_type = output_type
        wrapper._mutation_description = description or func.__doc__

        return wrapper

    return decorator


def confirm_action(
    *,
    title: Optional[str] = None,
    message: Optional[str] = None,
    confirm_label: str = "Confirmer",
    cancel_label: str = "Annuler",
    severity: str = "default",
    icon: Optional[str] = None,
    description: Optional[str] = None,
    permissions: Optional[List[str]] = None,
):
    """
    Decorator to expose a **confirmation-only** model method as a GraphQL mutation.

    The generated metadata carries enough UI hints for frontends to render a
    confirmation dialog (no additional inputs, only the record identifier).

    Example::
        @confirm_action(
            title=\"Valider l'ordre\",
            message=\"Confirmer la validation ?\",
            confirm_label=\"Valider\",
            severity=\"destructive\",
        )
        def validate(self):
            self.status = \"validated\"
            self.save()
            return True
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper._is_mutation = True
        wrapper._action_kind = "confirm"
        wrapper._action_ui = {
            "mode": "confirm",
            "title": title or func.__name__.replace("_", " ").title(),
            "message": message or description or func.__doc__,
            "confirm_label": confirm_label,
            "cancel_label": cancel_label,
            "severity": severity,
            "icon": icon,
        }
        wrapper._mutation_description = (description or message) or func.__doc__
        wrapper._requires_permissions = (
            permissions
            if permissions is not None
            else getattr(func, "_requires_permissions", None)
            or (
                [getattr(func, "_requires_permission", None)]
                if getattr(func, "_requires_permission", None)
                else None
            )
        )
        # Confirmation mutations are atomic by default
        wrapper._atomic = getattr(func, "_atomic", True)
        return wrapper

    return decorator


def action_form(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    submit_label: str = "Exécuter",
    cancel_label: str = "Annuler",
    icon: Optional[str] = None,
    severity: str = "default",
    fields: Optional[Dict[str, Dict[str, Any]]] = None,
    section: Optional[Dict[str, Any]] = None,
    ordering: Optional[List[str]] = None,
    returns: Optional[str] = None,
    on_finish: Optional[str] = None,
    permissions: Optional[List[str]] = None,
):
    """
    Decorator to expose a **form-based** model method as a GraphQL mutation.

    The method signature drives the generated input fields; UI hints are added so
    the frontend can render a small form dialog automatically.

    Example::
        @action_form(title=\"Planifier\", submit_label=\"Planifier\")
        def schedule(self, planned_start: date, planned_end: date | None = None):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper._is_mutation = True
        wrapper._action_kind = "form"
        wrapper._action_ui = {
            "mode": "form",
            "title": title or func.__name__.replace("_", " ").title(),
            "description": description or func.__doc__,
            "submit_label": submit_label,
            "cancel_label": cancel_label,
            "severity": severity,
            "icon": icon,
            "fields": fields or {},
            "section": section or {},
            "ordering": ordering or [],
            "returns": returns,
            "on_finish": on_finish,
        }
        wrapper._mutation_description = description or func.__doc__
        wrapper._requires_permissions = (
            permissions
            if permissions is not None
            else getattr(func, "_requires_permissions", None)
            or (
                [getattr(func, "_requires_permission", None)]
                if getattr(func, "_requires_permission", None)
                else None
            )
        )
        wrapper._atomic = getattr(func, "_atomic", True)
        return wrapper

    return decorator


def business_logic(
    category: str = "general",
    requires_permission: Optional[str] = None,
    atomic: bool = True,
):
    """
    Decorator to mark a method as custom business logic that should be exposed as a mutation.

    Args:
        category: Category of business logic (e.g., "workflow", "approval", "processing")
        requires_permission: Permission required to execute this mutation
        atomic: Whether to wrap execution in a database transaction

    Example:
        @business_logic(category="approval", requires_permission="can_approve_posts")
        def approve_post(self, approved_by: str, notes: str = ""):
            self.status = "approved"
            self.approved_by = approved_by
            self.approval_notes = notes
            self.approved_at = timezone.now()
            self.save()
            return {"status": "approved", "message": "Post approved successfully"}
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Mark as both mutation and business logic
        wrapper._is_mutation = True
        wrapper._is_business_logic = True
        wrapper._business_logic_category = category
        wrapper._requires_permission = requires_permission
        wrapper._atomic = atomic

        return wrapper

    return decorator


def private_method(func: Callable) -> Callable:
    """
    Decorator to mark a method as private (should not be exposed as a mutation).

    Example:
        @private_method
        def _internal_calculation(self):
            return self.value * 2
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    wrapper._private = True
    return wrapper


def custom_mutation_name(name: str):
    """
    Decorator to specify a custom name for the generated mutation.

    Args:
        name: Custom name for the mutation

    Example:
        @custom_mutation_name("publishArticle")
        def publish(self):
            self.is_published = True
            self.published_at = timezone.now()
            self.save()
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper._custom_mutation_name = name
        return wrapper

    return decorator


def register_schema(
    name: Optional[str] = None,
    description: str = "",
    version: str = "1.0.0",
    apps: Optional[List[str]] = None,
    models: Optional[List[str]] = None,
    settings: Optional[Dict[str, Any]] = None,
    auto_discovery: bool = True,
    enabled: bool = True,
):
    """
    Decorator for registering GraphQL schemas with the central schema registry.

    This decorator can be applied to schema classes or schema factory functions
    to automatically register them with the schema registry system.

    Args:
        name: Schema name (defaults to class/function name)
        description: Schema description for documentation
        version: Schema version string
        apps: List of Django apps this schema covers
        models: List of model names this schema includes
        settings: Schema-specific configuration settings
        auto_discovery: Whether to enable automatic model discovery
        enabled: Whether the schema is enabled by default

    Example:
        @register_schema(
            name="blog_schema",
            description="Blog management GraphQL schema",
            version="2.0.0",
            apps=["blog", "comments"],
            settings={"enable_graphiql": True, "authentication_required": False}
        )
        class BlogSchema(graphene.Schema):
            query = BlogQuery
            mutation = BlogMutation

        @register_schema(
            name="api_v1",
            description="Main API schema",
            apps=["users", "products"]
        )
        def create_api_schema():
            return graphene.Schema(query=APIQuery, mutation=APIMutation)
    """

    def decorator(schema_class_or_function: Callable) -> Callable:
        # Determine schema name
        schema_name = name or getattr(
            schema_class_or_function, "__name__", "unnamed_schema"
        )

        # Prepare registration data
        registration_data = {
            "name": schema_name,
            "description": description,
            "version": version,
            "apps": apps or [],
            "models": models or [],
            "settings": settings or {},
            "auto_discovery": auto_discovery,
            "enabled": enabled,
        }

        # Handle both class and function decoration
        if isinstance(schema_class_or_function, type):
            # Class decoration - register the class directly
            # Store registration metadata on the class
            schema_class_or_function._schema_registration = registration_data

            # Perform registration
            _register_schema_with_registry(schema_class_or_function, registration_data)

            return schema_class_or_function
        else:
            # Function decoration - register the function result
            @wraps(schema_class_or_function)
            def wrapper(*args, **kwargs):
                schema_instance = schema_class_or_function(*args, **kwargs)
                return schema_instance

            # Store registration metadata on the function
            wrapper._schema_registration = registration_data

            # Perform registration with function
            _register_schema_with_registry(schema_class_or_function, registration_data)

            return wrapper

    return decorator


def _register_schema_with_registry(
    schema_class_or_function: Callable, registration_data: Dict[str, Any]
):
    """
    Internal function to handle the actual schema registration with the registry.

    Args:
        schema_class_or_function: The schema class or factory function
        registration_data: Dictionary containing registration metadata
    """
    try:
        # Import registry here to avoid circular imports
        from .core.registry import schema_registry

        # Register the schema
        schema_registry.register_schema(
            name=registration_data["name"],
            description=registration_data["description"],
            apps=registration_data["apps"],
            models=registration_data["models"],
            settings=registration_data["settings"],
            enabled=registration_data["enabled"],
        )

        logger.info(
            f"Successfully registered schema '{registration_data['name']}' via decorator"
        )

    except ImportError as e:
        logger.warning(
            f"Could not register schema '{registration_data['name']}' - "
            f"registry not available: {e}"
        )
    except Exception as e:
        logger.error(
            f"Failed to register schema '{registration_data['name']}' via decorator: {e}"
        )
