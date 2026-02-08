"""
Authentication middleware for Rail Django GraphQL.

This module provides middleware for user authentication and field-level
permission enforcement for GraphQL operations.
"""

import logging
from typing import Any, Callable, Optional
from datetime import date, datetime, time
from decimal import Decimal

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from graphql import GraphQLError

from .base import BaseMiddleware
from ..security import get_auth_manager
from ..exceptions import ValidationError as GraphQLValidationError
from ...config_proxy import get_setting
from ...security import security, EventType, Outcome
from ...security.anomaly.detector import get_anomaly_detector
from ...security.field_permissions import (
    FieldAccessLevel,
    FieldContext,
    FieldVisibility,
    field_permission_manager,
)

logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseMiddleware):
    """Middleware for handling authentication.

    This middleware authenticates users via the configured auth manager
    and attaches the user to the request context.
    """

    def __init__(self, schema_name: Optional[str] = None):
        """Initialize authentication middleware.

        Args:
            schema_name: Optional schema name for schema-specific auth config.
        """
        super().__init__(schema_name)
        self.auth_manager = get_auth_manager(schema_name)

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Authenticate user and add to context.

        Args:
            next_resolver: Next resolver in the chain.
            root: Root value.
            info: GraphQL resolve info.
            **kwargs: Additional arguments.

        Returns:
            Resolver result.
        """
        if not self.settings.enable_authentication_middleware:
            return next_resolver(root, info, **kwargs)

        # Check if IP is blocked
        request = getattr(info.context, "request", None) or info.context
        if request and hasattr(request, "META"):
            client_ip = request.META.get("REMOTE_ADDR", "unknown")
            detector = get_anomaly_detector()
            if detector.is_ip_blocked(client_ip):
                security.emit(
                    EventType.AUTH_TOKEN_INVALID,
                    request=request,
                    outcome=Outcome.BLOCKED,
                    action="Request blocked: IP in blocklist",
                )
                raise GraphQLError("Access denied")

        # Authenticate user if not already done
        if not hasattr(info.context, 'user'):
            user = self.auth_manager.authenticate_user(info.context)
            info.context.user = user

        return next_resolver(root, info, **kwargs)


class FieldPermissionMiddleware(BaseMiddleware):
    """Middleware for field output masking and input enforcement.

    This middleware enforces field-level permissions for both input mutations
    and output field access based on user permissions and field configurations.
    """

    def __init__(self, schema_name: Optional[str] = None):
        """Initialize field permission middleware.

        Args:
            schema_name: Optional schema name for schema-specific permissions.
        """
        super().__init__(schema_name)
        self.input_mode = str(
            get_setting(
                "security_settings.field_permission_input_mode",
                "reject",
                schema_name,
            )
        ).lower()
        self.enable_field_permissions = bool(
            get_setting("security_settings.enable_field_permissions", True, schema_name)
        )

    def resolve(self, next_resolver: Callable, root: Any, info: Any, **kwargs) -> Any:
        """Apply field permission checks.

        Args:
            next_resolver: Next resolver in the chain.
            root: Root value.
            info: GraphQL resolve info.
            **kwargs: Additional arguments.

        Returns:
            Resolver result with permission masking applied.
        """
        if (
            not self.settings.enable_field_permission_middleware
            or not self.enable_field_permissions
        ):
            return next_resolver(root, info, **kwargs)

        if self._is_introspection_field(info):
            return next_resolver(root, info, **kwargs)

        user = getattr(info.context, "user", None)

        if self._is_root_field(info) and self._is_mutation(info):
            kwargs = self._enforce_input_permissions(user, info, kwargs)

        result = next_resolver(root, info, **kwargs)
        return self._apply_output_permissions(user, info, root, result)

    @staticmethod
    def _is_root_field(info: Any) -> bool:
        """Check if this is a root field resolution."""
        path = getattr(info, "path", None)
        if path is None:
            return True
        return getattr(path, "prev", None) is None

    @staticmethod
    def _is_introspection_field(info: Any) -> bool:
        """Check if this is an introspection field."""
        field_name = getattr(info, "field_name", "") or ""
        if field_name.startswith("__"):
            return True
        parent_type = getattr(info, "parent_type", None)
        parent_name = getattr(parent_type, "name", "") or ""
        return parent_name.startswith("__")

    @staticmethod
    def _is_mutation(info: Any) -> bool:
        """Check if this is a mutation operation."""
        operation = getattr(info, "operation", None)
        return bool(
            operation and getattr(operation, "operation", None) and
            operation.operation.value == "mutation"
        )

    @staticmethod
    def _unwrap_graphql_type(graphql_type: Any) -> Any:
        """Unwrap NonNull and List types to get the underlying type."""
        while hasattr(graphql_type, "of_type"):
            graphql_type = graphql_type.of_type
        return graphql_type

    @staticmethod
    def _coerce_masked_output_value(
        model_class: type[models.Model],
        field_name: str,
        result: Any,
        mask_value: Any,
    ) -> Any:
        """Return a mask value compatible with the GraphQL field scalar."""
        if mask_value is None:
            return None

        model_field = None
        try:
            model_field = model_class._meta.get_field(field_name)
        except (LookupError, FieldDoesNotExist, AttributeError):
            model_field = None

        if model_field is not None:
            def non_null_placeholder() -> Any:
                if isinstance(model_field, models.DecimalField):
                    return Decimal("0")
                if isinstance(model_field, models.FloatField):
                    return 0.0
                if isinstance(
                    model_field,
                    (
                        models.IntegerField,
                        models.BigIntegerField,
                        models.SmallIntegerField,
                        models.PositiveIntegerField,
                        models.PositiveSmallIntegerField,
                    ),
                ):
                    return 0
                if isinstance(model_field, models.BooleanField):
                    return False
                if isinstance(model_field, models.DateField) and not isinstance(
                    model_field, models.DateTimeField
                ):
                    return date(1970, 1, 1)
                if isinstance(model_field, models.DateTimeField):
                    return datetime(1970, 1, 1, 0, 0, 0)
                if isinstance(model_field, models.TimeField):
                    return time(0, 0, 0)
                if isinstance(model_field, models.DurationField):
                    return 0
                return None

            if model_field.is_relation:
                return None if model_field.null else result
            if isinstance(
                model_field,
                (
                    models.DecimalField,
                    models.FloatField,
                    models.IntegerField,
                    models.BigIntegerField,
                    models.SmallIntegerField,
                    models.PositiveIntegerField,
                    models.PositiveSmallIntegerField,
                    models.BooleanField,
                    models.DateField,
                    models.DateTimeField,
                    models.TimeField,
                    models.DurationField,
                ),
            ):
                if model_field.null:
                    return None
                return non_null_placeholder()
            return mask_value

        if isinstance(result, (Decimal, int, float, bool, date, datetime, time)):
            return None
        return mask_value

    def _resolve_parent_model_class(
        self, info: Any, root: Any, result: Any
    ) -> Optional[type[models.Model]]:
        """Resolve the Django model class for the parent type."""
        if isinstance(root, models.Model):
            return root.__class__
        parent_type = self._unwrap_graphql_type(getattr(info, "parent_type", None))
        graphene_type = getattr(parent_type, "graphene_type", None)
        meta = getattr(graphene_type, "_meta", None)
        model_class = getattr(meta, "model", None)
        if model_class is not None:
            return model_class
        if isinstance(result, models.Model):
            return result.__class__
        return None

    def _resolve_mutation_model_class(self, info: Any) -> Optional[type[models.Model]]:
        """Resolve the Django model class for a mutation return type."""
        graphql_type = self._unwrap_graphql_type(getattr(info, "return_type", None))
        graphene_type = getattr(graphql_type, "graphene_type", None)
        if graphene_type is None:
            return None
        model_class = getattr(graphene_type, "model_class", None)
        if model_class is not None:
            return model_class
        meta = getattr(graphene_type, "_meta", None)
        return getattr(meta, "model", None)

    def _resolve_operation_type(self, info: Any) -> str:
        """Resolve the operation type (read, create, update, delete)."""
        operation = getattr(info, "operation", None)
        op_value = (
            operation.operation.value
            if operation and getattr(operation, "operation", None)
            else "query"
        )
        if op_value == "mutation":
            return self._resolve_mutation_operation(info.field_name or "")
        return "read"

    @staticmethod
    def _resolve_mutation_operation(field_name: str) -> str:
        """Resolve the mutation operation type from the field name."""
        name = (field_name or "").lower()
        if name.startswith("bulk"):
            name = name[4:]
        if name.startswith(("create", "add", "register", "signup", "import")):
            return "create"
        if name.startswith(("delete", "remove", "archive", "purge", "clear")):
            return "delete"
        if name.startswith(("update", "set", "edit", "patch", "upsert", "enable", "disable")):
            return "update"
        if "delete" in name or "remove" in name:
            return "delete"
        if "create" in name or "add" in name:
            return "create"
        if "update" in name or "edit" in name or "patch" in name:
            return "update"
        return "write"

    @staticmethod
    def _normalize_payload(payload: Any) -> Optional[dict[str, Any]]:
        """Normalize various payload types to a dictionary."""
        if payload is None:
            return None
        if isinstance(payload, dict):
            return payload
        # Ensure 'items' is the dict-like method, not a GraphQL field named 'items'
        if hasattr(payload, "items") and callable(getattr(payload, "items", None)):
            try:
                return dict(payload.items())
            except Exception:
                pass
        if hasattr(payload, "__dict__"):
            return {
                key: value
                for key, value in vars(payload).items()
                if not key.startswith("_")
            }
        try:
            return dict(payload)
        except Exception:
            pass
        return None

    @staticmethod
    def _resolve_instance(
        model_class: type[models.Model], object_id: Any
    ) -> Optional[models.Model]:
        """Resolve a model instance by ID."""
        if object_id is None:
            return None
        try:
            return model_class.objects.get(pk=object_id)
        except Exception:
            try:
                from graphql_relay import from_global_id

                decoded_type, decoded_id = from_global_id(str(object_id))
                return model_class.objects.get(pk=decoded_id)
            except Exception:
                return None

    @staticmethod
    def _resolve_related_model(
        model_class: type[models.Model], field_name: str
    ) -> Optional[type[models.Model]]:
        """Resolve a related model class for a field."""
        if model_class is None:
            return None
        try:
            field = model_class._meta.get_field(field_name)
            related_model = getattr(field, "related_model", None)
            if related_model is not None:
                return related_model
        except Exception:
            pass
        try:
            for rel in model_class._meta.related_objects:
                accessor = rel.get_accessor_name()
                if accessor == field_name:
                    return rel.related_model
        except Exception:
            pass
        return None

    @staticmethod
    def _iter_nested_payloads(value: Any) -> list[dict[str, Any]]:
        """Iterate over nested payloads in a value."""
        nested_payloads: list[dict[str, Any]] = []
        if value is None:
            return []

        # Handle lists directly
        if isinstance(value, list):
            for item in value:
                normalized = FieldPermissionMiddleware._normalize_payload(item)
                if isinstance(normalized, dict):
                    nested_payloads.append(normalized)
            return nested_payloads

        # Normalize value (could be a dict or Graphene object)
        data = FieldPermissionMiddleware._normalize_payload(value)
        if not isinstance(data, dict):
            return []

        # Check for unified operation keys
        found_op = False
        for key in ("create", "update", "set"):
            if key in data:
                found_op = True
                val = data[key]
                if isinstance(val, list):
                    for item in val:
                        norm = FieldPermissionMiddleware._normalize_payload(item)
                        if isinstance(norm, dict):
                            nested_payloads.append(norm)
                else:
                    norm = FieldPermissionMiddleware._normalize_payload(val)
                    if isinstance(norm, dict):
                        nested_payloads.append(norm)

        # If no operation key found, check if it's a direct creation payload
        if not found_op:
            # Skip if it only contains connection/disconnection keys
            if not set(data.keys()).issubset({"connect", "disconnect", "set"}):
                nested_payloads.append(data)

        return nested_payloads

    def _enforce_input_permissions(
        self, user: Any, info: Any, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Enforce field permissions on mutation inputs."""
        model_class = self._resolve_mutation_model_class(info)
        if model_class is None:
            return kwargs

        operation = self._resolve_operation_type(info)
        if operation == "delete":
            return kwargs
        if operation == "write":
            operation = "update"

        request_context = {"request": getattr(info, "context", None)}
        disallowed_fields: list[str] = []
        updated_kwargs = dict(kwargs)

        def _check_payload(
            payload: Any,
            *,
            model_class: type[models.Model],
            object_id: Any = None,
        ) -> Any:
            payload_dict = self._normalize_payload(payload)
            if payload_dict is None:
                return payload
            target_payload = (
                payload_dict.get("data")
                if isinstance(payload_dict.get("data"), dict)
                else payload_dict
            )
            # Ensure we are working with a real dict to avoid AttrDict attribute collisions
            if not isinstance(target_payload, dict) or type(target_payload) is not dict:
                try:
                    target_payload = dict(target_payload)
                except Exception:
                    pass

            instance = None
            if object_id is not None:
                instance = self._resolve_instance(model_class, object_id)
            blocked = []
            for field_name in list(target_payload.keys()):
                if field_name in {"id", "pk", "object_id"}:
                    continue
                base_field = field_name
                if base_field.startswith("nested_"):
                    base_field = base_field[len("nested_"):]
                field_context = FieldContext(
                    user=user,
                    instance=instance,
                    field_name=base_field,
                    operation_type=operation,
                    model_class=model_class,
                    request_context=request_context,
                )
                access_level = field_permission_manager.get_field_access_level(
                    field_context
                )
                if access_level not in (
                    FieldAccessLevel.WRITE,
                    FieldAccessLevel.ADMIN,
                ):
                    blocked.append(field_name)
            if blocked and self.input_mode == "strip":
                for field_name in blocked:
                    target_payload.pop(field_name, None)
            disallowed_fields.extend(blocked)

            for field_name, value in list(target_payload.items()):
                if field_name in {"id", "pk", "object_id"}:
                    continue
                base_field = field_name
                if base_field.startswith("nested_"):
                    base_field = base_field[len("nested_"):]
                related_model = self._resolve_related_model(
                    model_class, base_field
                )
                if related_model is None:
                    continue
                for nested_payload in self._iter_nested_payloads(value):
                    nested_dict = self._normalize_payload(nested_payload)
                    if not isinstance(nested_dict, dict):
                        continue
                    nested_id = (
                        nested_dict.get("id")
                        or nested_dict.get("pk")
                        or nested_dict.get("object_id")
                    )
                    _check_payload(
                        nested_dict,
                        model_class=related_model,
                        object_id=nested_id,
                    )
            return payload_dict

        if "input" in updated_kwargs:
            object_id = updated_kwargs.get("id") or updated_kwargs.get("object_id")
            updated_kwargs["input"] = _check_payload(
                updated_kwargs["input"],
                model_class=model_class,
                object_id=object_id,
            )

        if "inputs" in updated_kwargs and isinstance(updated_kwargs["inputs"], list):
            sanitized_inputs = []
            for payload in updated_kwargs["inputs"]:
                payload_dict = self._normalize_payload(payload) or {}
                object_id = (
                    payload_dict.get("id")
                    or payload_dict.get("pk")
                    or payload_dict.get("object_id")
                )
                sanitized_inputs.append(
                    _check_payload(
                        payload,
                        model_class=model_class,
                        object_id=object_id,
                    )
                )
            updated_kwargs["inputs"] = sanitized_inputs

        if disallowed_fields and self.input_mode != "strip":
            raise GraphQLError(
                f"Input fields not permitted: {', '.join(sorted(set(disallowed_fields)))}"
            )

        return updated_kwargs

    def _apply_output_permissions(
        self, user: Any, info: Any, root: Any, result: Any
    ) -> Any:
        """Apply output permission masking to field results."""
        field_name = getattr(info, "field_name", None)
        if not field_name:
            return result
        model_class = self._resolve_parent_model_class(info, root, result)
        if model_class is None:
            return result

        instance = root if isinstance(root, models.Model) else None
        operation = self._resolve_operation_type(info)
        field_context = FieldContext(
            user=user,
            instance=instance,
            field_name=field_name,
            operation_type=operation,
            model_class=model_class,
            request_context={"request": getattr(info, "context", None)},
        )
        visibility, mask_value = field_permission_manager.get_field_visibility(
            field_context
        )

        if visibility == FieldVisibility.HIDDEN:
            return None
        if visibility == FieldVisibility.MASKED:
            return self._coerce_masked_output_value(
                model_class,
                field_name,
                result,
                mask_value,
            )
        if visibility == FieldVisibility.REDACTED:
            return self._redact_value(result)

        return result

    @staticmethod
    def _redact_value(value: Any) -> Any:
        """Redact a value for display."""
        if value is None:
            return None
        if isinstance(value, str):
            if len(value) > 4:
                return value[:2] + "*" * (len(value) - 4) + value[-2:]
            return "****"
        return "****"
