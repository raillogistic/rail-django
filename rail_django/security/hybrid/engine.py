"""
Hybrid RBAC + ABAC evaluation engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from django.db import models

from rail_django.config_proxy import get_setting

from ..abac.manager import ABACManager, abac_manager
from ..abac.types import ABACDecision
from ..rbac.manager import RoleManager, role_manager
from ..rbac.types import PermissionContext
from .strategies import CombinationStrategy

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


@dataclass
class HybridDecision:
    """Combined RBAC + ABAC decision."""

    allowed: bool
    rbac_allowed: Optional[bool] = None
    abac_allowed: Optional[bool] = None
    strategy: Optional[CombinationStrategy] = None
    reason: str = ""
    abac_decision: Optional[ABACDecision] = None


class HybridPermissionEngine:
    """Combines RBAC and ABAC decisions based on strategy."""

    def __init__(
        self,
        rbac: Optional[RoleManager] = None,
        abac: Optional[ABACManager] = None,
        strategy: Optional[CombinationStrategy] = None,
    ) -> None:
        self._rbac = rbac or role_manager
        self._abac = abac or abac_manager
        self._strategy = strategy or CombinationStrategy.RBAC_THEN_ABAC

    def has_permission(
        self,
        user: "AbstractUser",
        permission: str,
        context: Optional[PermissionContext] = None,
        instance: Optional[models.Model] = None,
        request: Any = None,
        info: Any = None,
        *,
        rbac_decision: Optional[bool] = None,
        schema_name: Optional[str] = None,
    ) -> HybridDecision:
        resolved_schema_name = (
            schema_name or self._resolve_schema_name(context=context, request=request)
        )
        if rbac_decision is None:
            if hasattr(self._rbac, "has_permission_rbac_only"):
                rbac_allowed = bool(
                    self._rbac.has_permission_rbac_only(user, permission, context)
                )
            else:
                rbac_allowed = bool(self._rbac.has_permission(user, permission, context))
        else:
            rbac_allowed = bool(rbac_decision)

        if not self._is_abac_enabled(schema_name=resolved_schema_name):
            return HybridDecision(
                allowed=rbac_allowed,
                rbac_allowed=rbac_allowed,
                strategy=self._resolve_strategy(schema_name=resolved_schema_name),
                reason="rbac_only",
            )

        model_class = context.model_class if context else None
        if instance is None and context is not None:
            instance = context.object_instance
        if request is None and context and isinstance(context.additional_context, dict):
            request = context.additional_context.get("request") or context.additional_context.get(
                "context"
            )

        abac_decision = self._abac.check_access(
            user=user,
            instance=instance,
            model_class=model_class,
            request=request,
            operation=context.operation if context else None,
            permission=permission,
            info=info,
            schema_name=resolved_schema_name,
        )
        abac_allowed = abac_decision.allowed if abac_decision is not None else None

        return self._combine(
            rbac_allowed,
            abac_allowed,
            abac_decision,
            schema_name=resolved_schema_name,
        )

    def _resolve_strategy(self, schema_name: Optional[str] = None) -> CombinationStrategy:
        configured = str(
            get_setting(
                "security_settings.hybrid_strategy",
                self._strategy.value,
                schema_name=schema_name,
            )
        ).lower()
        try:
            return CombinationStrategy(configured)
        except Exception:
            return self._strategy

    def _is_abac_enabled(self, schema_name: Optional[str] = None) -> bool:
        return bool(
            get_setting(
                "security_settings.enable_abac",
                False,
                schema_name=schema_name,
            )
        )

    def _resolve_schema_name(
        self, *, context: Optional[PermissionContext], request: Any
    ) -> Optional[str]:
        if request is not None:
            value = getattr(request, "schema_name", None)
            if value:
                return str(value)
        if context is not None and isinstance(context.additional_context, dict):
            req = context.additional_context.get("request") or context.additional_context.get(
                "context"
            )
            value = getattr(req, "schema_name", None)
            if value:
                return str(value)
        return None

    def _combine(
        self,
        rbac: bool,
        abac: Optional[bool],
        abac_decision: Optional[ABACDecision],
        *,
        schema_name: Optional[str] = None,
    ) -> HybridDecision:
        strategy = self._resolve_strategy(schema_name=schema_name)

        if abac is None:
            return HybridDecision(
                allowed=rbac,
                rbac_allowed=rbac,
                strategy=strategy,
                reason="abac_no_decision",
                abac_decision=abac_decision,
            )

        if strategy == CombinationStrategy.RBAC_AND_ABAC:
            allowed = rbac and abac
        elif strategy == CombinationStrategy.RBAC_OR_ABAC:
            allowed = rbac or abac
        elif strategy == CombinationStrategy.ABAC_OVERRIDE:
            allowed = abac
        elif strategy == CombinationStrategy.RBAC_THEN_ABAC:
            allowed = abac if rbac else False
        elif strategy == CombinationStrategy.MOST_RESTRICTIVE:
            allowed = rbac and abac
        else:
            allowed = rbac and abac

        return HybridDecision(
            allowed=allowed,
            rbac_allowed=rbac,
            abac_allowed=abac,
            strategy=strategy,
            reason=f"{strategy.value}:rbac={rbac},abac={abac}",
            abac_decision=abac_decision,
        )


hybrid_engine = HybridPermissionEngine()
