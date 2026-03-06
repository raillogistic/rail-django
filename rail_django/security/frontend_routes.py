"""
Frontend route access registry.

Provides a small, backend-configurable registry that maps frontend route and
navigation identifiers to role/permission requirements. The frontend uses this
as UX metadata only; backend APIs must still enforce authorization directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .rbac import role_manager

ALLOWED_TARGET_TYPES = {
    "project",
    "route",
    "navigation-group",
    "navigation-entry",
}


def _normalize_values(values: Optional[Iterable[object]]) -> tuple[str, ...]:
    if values is None:
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = str(value or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return tuple(normalized)


def _normalize_target_type(value: object) -> str:
    return str(value or "").strip().lower().replace("_", "-")


@dataclass(frozen=True)
class FrontendRouteAccessRule:
    target_type: str
    target: str
    require_authentication: bool = True
    any_permissions: tuple[str, ...] = field(default_factory=tuple)
    all_permissions: tuple[str, ...] = field(default_factory=tuple)
    any_roles: tuple[str, ...] = field(default_factory=tuple)
    all_roles: tuple[str, ...] = field(default_factory=tuple)
    source: str = "code"

    def __post_init__(self) -> None:
        normalized_target_type = _normalize_target_type(self.target_type)
        if normalized_target_type not in ALLOWED_TARGET_TYPES:
            raise ValueError(
                f"Unsupported frontend route target type '{self.target_type}'."
            )
        normalized_target = str(self.target or "").strip()
        if not normalized_target:
            raise ValueError("Frontend route access rule target is required.")

        object.__setattr__(self, "target_type", normalized_target_type)
        object.__setattr__(self, "target", normalized_target)
        object.__setattr__(
            self, "any_permissions", _normalize_values(self.any_permissions)
        )
        object.__setattr__(
            self, "all_permissions", _normalize_values(self.all_permissions)
        )
        object.__setattr__(self, "any_roles", _normalize_values(self.any_roles))
        object.__setattr__(self, "all_roles", _normalize_values(self.all_roles))
        object.__setattr__(self, "source", str(self.source or "code"))

    def to_payload(self, user: Any = None) -> dict[str, Any]:
        allowed, denial_reason = frontend_route_access_registry.evaluate(user, self)
        return {
            "target_type": self.target_type,
            "target": self.target,
            "require_authentication": self.require_authentication,
            "any_permissions": list(self.any_permissions),
            "all_permissions": list(self.all_permissions),
            "any_roles": list(self.any_roles),
            "all_roles": list(self.all_roles),
            "allowed": allowed,
            "denial_reason": denial_reason,
        }


def build_frontend_route_access_rule(
    payload: dict[str, Any],
    *,
    source: str = "code",
) -> FrontendRouteAccessRule:
    if not isinstance(payload, dict):
        raise ValueError("Frontend route access rule payload must be an object.")

    return FrontendRouteAccessRule(
        target_type=str(payload.get("target_type") or payload.get("targetType") or ""),
        target=str(payload.get("target") or ""),
        require_authentication=bool(
            payload.get("require_authentication", payload.get("requireAuthentication", True))
        ),
        any_permissions=_normalize_values(
            payload.get("any_permissions") or payload.get("anyPermissions")
        ),
        all_permissions=_normalize_values(
            payload.get("all_permissions") or payload.get("allPermissions")
        ),
        any_roles=_normalize_values(payload.get("any_roles") or payload.get("anyRoles")),
        all_roles=_normalize_values(payload.get("all_roles") or payload.get("allRoles")),
        source=source,
    )


class FrontendRouteAccessRegistry:
    def __init__(self) -> None:
        self._rules: list[FrontendRouteAccessRule] = []

    def clear(self) -> None:
        self._rules.clear()

    def register(self, rule: FrontendRouteAccessRule | dict[str, Any]) -> None:
        normalized = (
            build_frontend_route_access_rule(rule)
            if isinstance(rule, dict)
            else rule
        )
        if normalized in self._rules:
            return
        self._rules.append(normalized)

    def register_many(
        self,
        rules: Iterable[FrontendRouteAccessRule | dict[str, Any]],
        *,
        source: str = "code",
    ) -> None:
        for rule in rules:
            if isinstance(rule, dict):
                self.register(build_frontend_route_access_rule(rule, source=source))
            else:
                self.register(rule)

    def get_rules(self) -> list[FrontendRouteAccessRule]:
        return list(self._rules)

    def evaluate(
        self,
        user: Any,
        rule: FrontendRouteAccessRule,
    ) -> tuple[bool, Optional[str]]:
        is_authenticated = bool(user and getattr(user, "is_authenticated", False))

        if rule.require_authentication and not is_authenticated:
            return False, "Authentication required"

        has_role_requirements = bool(rule.any_roles or rule.all_roles)
        has_permission_requirements = bool(
            rule.any_permissions or rule.all_permissions
        )
        if not is_authenticated and (has_role_requirements or has_permission_requirements):
            if has_role_requirements:
                return False, "Authentication required for role-based access"
            return False, "Authentication required for permission-based access"

        if getattr(user, "is_superuser", False):
            return True, None

        user_roles = set(role_manager.get_user_roles(user)) if is_authenticated else set()

        if rule.any_roles and not any(role in user_roles for role in rule.any_roles):
            return False, f"Role required: {', '.join(rule.any_roles)}"

        missing_roles = [role for role in rule.all_roles if role not in user_roles]
        if missing_roles:
            return False, f"Role required: {', '.join(missing_roles)}"

        if rule.any_permissions and not any(
            role_manager.has_permission(user, permission)
            for permission in rule.any_permissions
        ):
            return False, f"Permission required: {', '.join(rule.any_permissions)}"

        missing_permissions = [
            permission
            for permission in rule.all_permissions
            if not role_manager.has_permission(user, permission)
        ]
        if missing_permissions:
            return False, f"Permission required: {', '.join(missing_permissions)}"

        return True, None

    def snapshot_for_user(self, user: Any) -> list[dict[str, Any]]:
        return [rule.to_payload(user) for rule in self._rules]


def load_frontend_route_access_from_payload(
    payload: object,
    *,
    source: str,
) -> int:
    if not isinstance(payload, dict):
        return 0

    rules = payload.get("frontend_route_access")
    if rules is None:
        return 0
    if not isinstance(rules, list):
        raise ValueError(
            f"frontend_route_access in {source} must be declared as a list."
        )

    count = 0
    for entry in rules:
        frontend_route_access_registry.register(
            build_frontend_route_access_rule(entry, source=source)
        )
        count += 1
    return count


frontend_route_access_registry = FrontendRouteAccessRegistry()


__all__ = [
    "ALLOWED_TARGET_TYPES",
    "FrontendRouteAccessRule",
    "FrontendRouteAccessRegistry",
    "build_frontend_route_access_rule",
    "frontend_route_access_registry",
    "load_frontend_route_access_from_payload",
]
