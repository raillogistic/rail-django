"""
Field Permission Manager for Django GraphQL.

This module provides the FieldPermissionManager class which handles:
- Dynamic field-level permissions
- Relationship-based filtering
- Conditional field masking
- Real-time access validation
"""

import logging
from typing import TYPE_CHECKING, Any, Optional, Type, Union

from django.db import models

from rail_django.config_proxy import get_setting

from ..policies import PolicyContext as AccessPolicyContext
from ..policies import PolicyEffect, policy_manager
from .defaults import (
    DEFAULT_CLASSIFICATION_PATTERNS,
    DEFAULT_SENSITIVE_FIELDS,
    is_owner_or_admin,
    setup_default_rules,
)
from .types import (
    FieldAccessLevel,
    FieldContext,
    FieldPermissionRule,
    FieldVisibility,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


class FieldPermissionManager:
    """Manager for field-level permissions with wildcard and policy engine support."""

    def __init__(self) -> None:
        """Initialize the field permission manager."""
        self._field_rules: dict[str, list[FieldPermissionRule]] = {}
        self._pattern_rules: dict[str, list[FieldPermissionRule]] = {}
        self._global_rules: list[FieldPermissionRule] = []
        self._graphql_configs: set[str] = set()
        self._rule_signatures: set[tuple] = set()
        self._model_classifications: dict[str, set[str]] = {}
        self._field_classifications: dict[str, dict[str, set[str]]] = {}
        self._policy_engine_enabled = bool(
            get_setting("security_settings.enable_policy_engine", True)
        )
        self._sensitive_fields = DEFAULT_SENSITIVE_FIELDS.copy()
        self._classification_defaults = {
            k: v.copy() for k, v in DEFAULT_CLASSIFICATION_PATTERNS.items()
        }
        setup_default_rules(self)

    def _safe_has_perm(self, user: Any, perm_name: str) -> bool:
        """Safely check if user has a permission."""
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "pk", None) is None:
            return False
        try:
            return user.has_perm(perm_name)
        except Exception:
            return False

    def _safe_signature_value(self, value: Any) -> Any:
        """Convert value to a hashable form for signature computation."""
        try:
            hash(value)
        except TypeError:
            return repr(value)
        return value

    def _rule_signature(self, rule: FieldPermissionRule) -> tuple:
        """Generate a unique signature for a rule to prevent duplicates."""
        roles = tuple(sorted(rule.roles or []))
        permissions = tuple(sorted(rule.permissions or []))
        return (
            rule.model_name, rule.field_name, rule.access_level, rule.visibility,
            self._safe_signature_value(rule.mask_value), roles, permissions,
            bool(rule.context_required), self._safe_signature_value(rule.condition),
        )

    def register_field_rule(self, rule: FieldPermissionRule) -> None:
        """Register a permission rule for a field."""
        key = f"{rule.model_name}.{rule.field_name}"
        signature = self._rule_signature(rule)
        if signature in self._rule_signatures:
            logger.debug("Field permission rule already registered for %s", key)
            return
        self._rule_signatures.add(signature)

        if key not in self._field_rules:
            self._field_rules[key] = []
        self._field_rules[key].append(rule)

        if "*" in rule.field_name and rule.field_name != "*":
            pattern_key = rule.model_name or "*"
            if pattern_key not in self._pattern_rules:
                self._pattern_rules[pattern_key] = []
            self._pattern_rules[pattern_key].append(rule)

        logger.info(
            "Field permission rule registered for %s (access=%s visibility=%s)",
            key,
            rule.access_level.value if rule.access_level else None,
            rule.visibility.value if rule.visibility else None,
        )

    def _iter_field_rules(self, context: FieldContext) -> list[FieldPermissionRule]:
        """Iterate over all applicable rules for a field context."""
        field_name = context.field_name
        lookup_tokens = self._get_model_lookup_tokens(context.instance, context.model_class)
        yielded: list[FieldPermissionRule] = []
        seen_keys: set[str] = set()

        for token in lookup_tokens:
            exact_key = f"{token}.{field_name}"
            if exact_key in self._field_rules and exact_key not in seen_keys:
                yielded.extend(self._field_rules[exact_key])
                seen_keys.add(exact_key)

            pattern_rules = self._pattern_rules.get(token, [])
            if pattern_rules:
                yielded.extend(pattern_rules)

            wildcard_key = f"{token}.*"
            if wildcard_key in self._field_rules and wildcard_key not in seen_keys:
                yielded.extend(self._field_rules[wildcard_key])
                seen_keys.add(wildcard_key)
        return yielded

    def register_global_rule(self, rule: FieldPermissionRule) -> None:
        """Register a global rule applicable to all models."""
        self._global_rules.append(rule)
        logger.info(f"Global rule registered for {rule.field_name}")

    def register_graphql_field_config(
        self, model_class: Type[models.Model], graphql_meta: Any
    ) -> None:
        """Create rules based on a model's GraphQL configuration."""
        if not model_class or not graphql_meta:
            return
        model_label = model_class._meta.label_lower
        if model_label in self._graphql_configs:
            return

        field_config = getattr(graphql_meta, "field_config", None)
        if not field_config:
            return

        def _rules_from_fields(
            field_names: list[str], access: FieldAccessLevel,
            visibility: FieldVisibility, mask_value: Any = None
        ) -> None:
            for field_name in field_names:
                self.register_field_rule(FieldPermissionRule(
                    field_name=field_name, model_name=model_label,
                    access_level=access, visibility=visibility, mask_value=mask_value,
                ))

        if field_config.exclude:
            _rules_from_fields(field_config.exclude, FieldAccessLevel.NONE, FieldVisibility.HIDDEN)
        if field_config.read_only:
            _rules_from_fields(field_config.read_only, FieldAccessLevel.READ, FieldVisibility.VISIBLE)
        if field_config.write_only:
            _rules_from_fields(field_config.write_only, FieldAccessLevel.WRITE, FieldVisibility.HIDDEN)
        self._graphql_configs.add(model_label)

    def _get_model_lookup_tokens(
        self, instance: Optional[models.Model], model_class: Optional[Type[models.Model]]
    ) -> list[str]:
        """Return possible identifiers (label + name) for a model."""
        tokens: list[str] = []
        target_class = instance.__class__ if instance is not None else model_class
        if target_class is not None:
            tokens.extend([target_class._meta.label_lower, target_class.__name__])
        tokens.append("*")
        return [t for i, t in enumerate(tokens) if t and t not in tokens[:i]]

    def register_classification_tags(
        self, model_class: Union[Type[models.Model], str], *,
        model_tags: Optional[list[str]] = None, field_tags: Optional[dict[str, list[str]]] = None,
    ) -> None:
        """Register classification tags for a model or its fields."""
        if not model_class:
            return
        model_key = model_class.lower() if isinstance(model_class, str) else model_class._meta.label_lower

        if model_tags:
            tags = {str(tag) for tag in model_tags if tag}
            if tags:
                self._model_classifications.setdefault(model_key, set()).update(tags)

        if field_tags:
            field_map = self._field_classifications.setdefault(model_key, {})
            for field_name, tags in field_tags.items():
                if field_name and tags:
                    normalized = {str(tag) for tag in tags if tag}
                    if normalized:
                        field_map.setdefault(field_name, set()).update(normalized)

    def _match_pattern(self, value: str, pattern: str) -> bool:
        """Match a value against a pattern with wildcard support."""
        if not value:
            return False
        if pattern == "*" or pattern == value:
            return True
        if "*" in pattern:
            return pattern.replace("*", "") in value
        return False

    def _coerce_access_level(self, value: Any) -> Optional[FieldAccessLevel]:
        """Convert a value to FieldAccessLevel enum."""
        if value is None:
            return None
        if isinstance(value, FieldAccessLevel):
            return value
        mapping = {"none": FieldAccessLevel.NONE, "read": FieldAccessLevel.READ,
                   "write": FieldAccessLevel.WRITE, "admin": FieldAccessLevel.ADMIN}
        return mapping.get(str(value).lower())

    def _coerce_visibility(self, value: Any) -> Optional[FieldVisibility]:
        """Convert a value to FieldVisibility enum."""
        if value is None:
            return None
        if isinstance(value, FieldVisibility):
            return value
        mapping = {"visible": FieldVisibility.VISIBLE, "hidden": FieldVisibility.HIDDEN,
                   "masked": FieldVisibility.MASKED, "redacted": FieldVisibility.REDACTED}
        return mapping.get(str(value).lower())

    def _get_classifications(self, context: FieldContext) -> set[str]:
        """Get all classification tags for a field context."""
        tags: set[str] = set(context.classifications or [])
        model_key = None
        if context.model_class is not None:
            model_key = context.model_class._meta.label_lower
        elif context.instance is not None:
            model_key = context.instance.__class__._meta.label_lower

        if model_key:
            tags.update(self._model_classifications.get(model_key, set()))
        tags.update(self._model_classifications.get("*", set()))

        field_name = context.field_name or ""
        if field_name:
            for lookup_key in (model_key, "*"):
                if lookup_key:
                    for pattern, values in self._field_classifications.get(lookup_key, {}).items():
                        if self._match_pattern(field_name, pattern):
                            tags.update(values)
            for default_tag, patterns in self._classification_defaults.items():
                if any(self._match_pattern(field_name, p) for p in patterns):
                    tags.add(default_tag)
        context.classifications = tags
        return tags

    def _build_policy_context(self, context: FieldContext) -> AccessPolicyContext:
        """Build a policy context from a field context."""
        model_class = context.model_class
        if model_class is None and context.instance is not None:
            model_class = context.instance.__class__
        object_id = getattr(context.instance, "pk", None) if context.instance else None
        classifications = self._get_classifications(context)
        additional_context = context.request_context
        request = None
        if isinstance(additional_context, dict):
            request = additional_context.get("request") or additional_context.get("context")
        return AccessPolicyContext(
            user=context.user, permission=None, model_class=model_class,
            field_name=context.field_name, operation=context.operation_type,
            object_instance=context.instance,
            object_id=str(object_id) if object_id is not None else None,
            classifications=classifications, additional_context=additional_context, request=request,
        )

    def _get_policy_override(
        self, context: FieldContext
    ) -> Optional[tuple[FieldAccessLevel, FieldVisibility, Any]]:
        """Get policy engine override for a field context."""
        if not self._policy_engine_enabled:
            return None
        policy_context = self._build_policy_context(context)
        decision = policy_manager.evaluate(policy_context)
        if decision is None:
            return None

        access_level = self._coerce_access_level(decision.policy.access_level)
        visibility = self._coerce_visibility(decision.policy.visibility)
        mask_value = decision.policy.mask_value

        if decision.effect == PolicyEffect.DENY:
            access_level = access_level or FieldAccessLevel.NONE
            visibility = visibility or FieldVisibility.HIDDEN
        else:
            access_level = access_level or FieldAccessLevel.READ
            visibility = visibility or FieldVisibility.VISIBLE
        return access_level, visibility, mask_value

    def get_field_access_level(self, context: FieldContext) -> FieldAccessLevel:
        """Determine the access level for a field."""
        if context.user is None:
            return FieldAccessLevel.NONE

        policy_override = self._get_policy_override(context)
        if policy_override:
            return policy_override[0]

        if context.user.is_superuser:
            return FieldAccessLevel.ADMIN

        for rule in self._iter_field_rules(context):
            if self._rule_applies(rule, context):
                return rule.access_level

        for rule in self._global_rules:
            if self._rule_applies(rule, context):
                return rule.access_level

        target_model = context.model_class
        if target_model is None and context.instance is not None:
            target_model = context.instance.__class__

        if target_model is not None and context.user.is_authenticated:
            app_label = target_model._meta.app_label
            model_name_lower = target_model._meta.model_name
            if context.operation_type in ["create", "update", "delete"]:
                if self._safe_has_perm(context.user, f"{app_label}.change_{model_name_lower}"):
                    return FieldAccessLevel.WRITE
            if self._safe_has_perm(context.user, f"{app_label}.view_{model_name_lower}"):
                return FieldAccessLevel.READ

        return FieldAccessLevel.READ

    def get_field_visibility(self, context: FieldContext) -> tuple[FieldVisibility, Any]:
        """Determine the visibility of a field and its mask value if applicable."""
        if context.user is None:
            return FieldVisibility.HIDDEN, None

        policy_override = self._get_policy_override(context)
        if policy_override:
            return policy_override[1], policy_override[2]

        access_level = self.get_field_access_level(context)
        if access_level == FieldAccessLevel.NONE:
            return FieldVisibility.HIDDEN, None

        for rule in self._iter_field_rules(context):
            if self._rule_applies(rule, context):
                return rule.visibility, rule.mask_value

        for rule in self._global_rules:
            if self._rule_applies(rule, context):
                return rule.visibility, rule.mask_value

        if self._is_sensitive_field(context.field_name):
            return FieldVisibility.MASKED, "***HIDDEN***"
        return FieldVisibility.VISIBLE, None

    def _rule_applies(self, rule: FieldPermissionRule, context: FieldContext) -> bool:
        """Check if a rule applies to the given context."""
        if rule.model_name not in ("*", None):
            identifiers = self._get_model_lookup_tokens(context.instance, context.model_class)
            if rule.model_name not in identifiers:
                return False

        if rule.field_name != "*":
            if "*" in rule.field_name:
                if rule.field_name.replace("*", "") not in context.field_name:
                    return False
            elif rule.field_name != context.field_name:
                return False

        if rule.roles:
            from ..rbac import role_manager
            user_roles = role_manager.get_user_roles(context.user)
            if not any(role in user_roles for role in rule.roles):
                return False

        if rule.permissions:
            if not any(self._safe_has_perm(context.user, perm) for perm in rule.permissions):
                return False

        if rule.condition:
            try:
                if not rule.condition(context):
                    return False
            except Exception as e:
                logger.error(f"Error in rule condition: {e}")
                return False
        return True

    def _is_sensitive_field(self, field_name: str) -> bool:
        """Check if a field is considered sensitive."""
        field_lower = field_name.lower()
        return any(sensitive in field_lower for sensitive in self._sensitive_fields)

    # Keep reference to is_owner_or_admin for backward compatibility
    _is_owner_or_admin = staticmethod(is_owner_or_admin)

    def filter_fields_for_user(
        self, user: "AbstractUser", model_class: Type[models.Model],
        instance: Optional[models.Model] = None,
    ) -> dict[str, Any]:
        """Filter visible fields for a user."""
        result = {}
        for field in model_class._meta.get_fields():
            if field.name.startswith("_"):
                continue
            context = FieldContext(
                user=user, instance=instance, field_name=field.name,
                operation_type="read", model_class=model_class,
            )
            access_level = self.get_field_access_level(context)
            visibility, mask_value = self.get_field_visibility(context)

            if visibility != FieldVisibility.HIDDEN:
                result[field.name] = {
                    "access_level": access_level.value,
                    "visibility": visibility.value,
                    "mask_value": mask_value,
                    "readable": access_level in [FieldAccessLevel.READ, FieldAccessLevel.WRITE, FieldAccessLevel.ADMIN],
                    "writable": access_level in [FieldAccessLevel.WRITE, FieldAccessLevel.ADMIN],
                }
        return result

    def apply_field_filtering(
        self, queryset: models.QuerySet, user: "AbstractUser"
    ) -> models.QuerySet:
        """Apply field filtering to a QuerySet."""
        if not user or not user.is_authenticated:
            return queryset.none()
        if user.is_superuser:
            return queryset
        return queryset


# Global field permission manager instance
field_permission_manager = FieldPermissionManager()
