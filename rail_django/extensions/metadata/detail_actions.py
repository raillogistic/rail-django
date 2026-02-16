"""
Detail action extraction and runtime helpers.

This module keeps detail action concerns isolated from query assembly so the
detail contract can expose stable action metadata while preserving existing
mutation naming conventions.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any, Callable, Mapping, Sequence

logger = logging.getLogger(__name__)

_TEMPLATE_TOKEN = re.compile(r"^\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}$")


def extract_detail_action_definitions(
    model_schema: Mapping[str, Any],
    *,
    object_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Build metadata-defined detail actions from model schema mutation metadata.

    The extractor intentionally keeps the contract additive: existing mutation
    names remain the execution targets and detail-specific fields are derived
    from the mutation `action` payload when present.
    """
    actions: list[dict[str, Any]] = []
    for mutation in model_schema.get("mutations", []) or []:
        if not isinstance(mutation, Mapping):
            continue

        mutation_name = str(mutation.get("name") or "").strip()
        if not mutation_name:
            continue

        # Detail actions only include mutating operations.
        operation = str(mutation.get("operation") or "").strip().lower()
        if operation in {"list", "retrieve"}:
            continue

        action_payload = mutation.get("action")
        action_meta = action_payload if isinstance(action_payload, Mapping) else {}
        action_key = str(action_meta.get("key") or mutation_name).strip()
        action_scope = str(action_meta.get("scope") or "MODEL").upper()
        action_label = str(action_meta.get("title") or action_key).strip()

        input_template = action_meta.get("input_template")
        if not isinstance(input_template, Mapping):
            input_template = {"id": "{{record.id}}"} if object_id else {}

        actions.append(
            {
                "key": action_key,
                "label": action_label or mutation_name,
                "scope": action_scope,
                "mutation_name": mutation_name,
                "input_template": input_template,
                "confirmation_template": action_meta.get("message"),
                "permission_key": ",".join(
                    str(entry)
                    for entry in (mutation.get("required_permissions") or [])
                    if entry
                ),
                "audit_enabled": True,
                "allowed": bool(mutation.get("allowed", False)),
                "reason": mutation.get("reason"),
            }
        )
    return actions


def bind_action_template(
    template: Any,
    context: Mapping[str, Any],
) -> Any:
    """
    Resolve `{{path.to.value}}` placeholders recursively in action templates.
    """

    if isinstance(template, Mapping):
        return {key: bind_action_template(value, context) for key, value in template.items()}
    if isinstance(template, Sequence) and not isinstance(template, (str, bytes)):
        return [bind_action_template(value, context) for value in template]
    if not isinstance(template, str):
        return template

    token_match = _TEMPLATE_TOKEN.match(template.strip())
    if not token_match:
        return template

    token = token_match.group(1)
    current: Any = context
    for segment in token.split("."):
        if isinstance(current, Mapping) and segment in current:
            current = current[segment]
        else:
            return None
    return current


def emit_action_audit_event(
    *,
    action_key: str,
    model_name: str,
    record_id: str,
    actor_id: str | None,
    outcome: str,
    sink: Callable[[dict[str, Any]], None] | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    """
    Build and optionally emit an action-attempt audit payload.

    The sink callback lets callers wire persistence without coupling this module
    to a specific audit backend.
    """
    payload = {
        "action_key": action_key,
        "model_name": model_name,
        "record_id": record_id,
        "actor_id": actor_id,
        "attempt_at": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
        "error_code": error_code,
    }
    if sink is not None:
        try:
            sink(payload)
        except Exception:
            logger.exception("Failed to emit detail action audit event")
    return payload


def resolve_detail_action_execution(
    action_definitions: Sequence[Mapping[str, Any]],
    *,
    action_key: str,
    context: Mapping[str, Any],
    available_mutations: Sequence[str] | None = None,
) -> dict[str, Any]:
    """
    Resolve one detail action into a permission-gated mutation execution plan.
    """
    action = next(
        (
            entry
            for entry in action_definitions
            if str(entry.get("key") or "").strip() == str(action_key or "").strip()
        ),
        None,
    )
    if not action:
        return {
            "ok": False,
            "denied": True,
            "reason": "Action not found",
            "action": None,
            "mutation_name": None,
            "payload": {},
        }

    allowed = bool(action.get("allowed", False))
    if not allowed:
        return {
            "ok": False,
            "denied": True,
            "reason": str(action.get("reason") or "Action denied"),
            "action": dict(action),
            "mutation_name": None,
            "payload": {},
        }

    mutation_name = str(action.get("mutation_name") or "").strip()
    if not mutation_name:
        return {
            "ok": False,
            "denied": True,
            "reason": "Mutation name missing",
            "action": dict(action),
            "mutation_name": None,
            "payload": {},
        }

    allowed_mutation_names = {
        str(name).strip()
        for name in (available_mutations or [])
        if str(name).strip()
    }
    if allowed_mutation_names and mutation_name not in allowed_mutation_names:
        return {
            "ok": False,
            "denied": True,
            "reason": "Mutation unavailable",
            "action": dict(action),
            "mutation_name": None,
            "payload": {},
        }

    input_template = action.get("input_template")
    if not isinstance(input_template, Mapping):
        input_template = {}
    payload = bind_action_template(input_template, context)
    if not isinstance(payload, Mapping):
        payload = {}

    return {
        "ok": True,
        "denied": False,
        "reason": None,
        "action": dict(action),
        "mutation_name": mutation_name,
        "payload": dict(payload),
    }


def execute_detail_action(
    action_definitions: Sequence[Mapping[str, Any]],
    *,
    action_key: str,
    context: Mapping[str, Any],
    model_name: str,
    record_id: str,
    actor_id: str | None,
    available_mutations: Sequence[str] | None = None,
    execute: Callable[[str, Mapping[str, Any]], Any] | None = None,
    sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """
    Execute one detail action plan and emit an audit event for all outcomes.
    """
    plan = resolve_detail_action_execution(
        action_definitions,
        action_key=action_key,
        context=context,
        available_mutations=available_mutations,
    )
    if not plan["ok"]:
        audit_event = emit_action_audit_event(
            action_key=action_key,
            model_name=model_name,
            record_id=record_id,
            actor_id=actor_id,
            outcome="DENIED",
            sink=sink,
            error_code="denied",
        )
        return {
            **plan,
            "outcome": "DENIED",
            "error_code": "denied",
            "audit_event": audit_event,
        }

    mutation_name = str(plan.get("mutation_name") or "").strip()
    payload = plan.get("payload") or {}

    outcome = "ALLOWED_SUCCESS"
    error_code = None
    mutation_response: Any = None
    if execute is not None:
        try:
            mutation_response = execute(mutation_name, payload)
            response_ok = (
                bool(mutation_response)
                if not isinstance(mutation_response, Mapping)
                else bool(mutation_response.get("ok", False))
            )
            if not response_ok:
                outcome = "ALLOWED_FAILURE"
                if isinstance(mutation_response, Mapping):
                    error_code = mutation_response.get("error_code")
        except Exception:
            outcome = "ALLOWED_FAILURE"
            error_code = "execution_error"

    audit_event = emit_action_audit_event(
        action_key=action_key,
        model_name=model_name,
        record_id=record_id,
        actor_id=actor_id,
        outcome=outcome,
        sink=sink,
        error_code=str(error_code) if error_code else None,
    )
    return {
        **plan,
        "ok": outcome == "ALLOWED_SUCCESS",
        "denied": False,
        "outcome": outcome,
        "error_code": str(error_code) if error_code else None,
        "response": mutation_response,
        "audit_event": audit_event,
    }
