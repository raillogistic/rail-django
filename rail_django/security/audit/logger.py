"""
AuditLogger implementation.
"""

import json
import logging
from dataclasses import asdict
from django.core.serializers.json import DjangoJSONEncoder
from .types import AuditEvent, AuditEventType, AuditSeverity
from .utils import _json_safe

logger = logging.getLogger(__name__)


class AuditLogger:
    """Gestionnaire de journalisation d'audit."""

    def __init__(self):
        self.logger = logging.getLogger("audit")
        self._event_handlers = {}
        self._risk_calculators = {}
        self.sensitive_fields = {"password", "token", "secret", "key", "hash", "ssn", "social_security", "credit_card", "bank_account", "email", "phone", "address"}
        high_risk = {"delete", "bulk_delete", "user_delete", "permission_change", "role_change", "password_reset", "mfa_disable"}
        self.high_risk_operations = high_risk
        self._setup_default_risk_calculators()

    def _setup_default_risk_calculators(self):
        self.register_risk_calculator(AuditEventType.LOGIN_FAILURE, self._calculate_login_failure_risk)
        self.register_risk_calculator(AuditEventType.PERMISSION_DENIED, self._calculate_permission_denied_risk)
        self.register_risk_calculator(AuditEventType.SENSITIVE_DATA_ACCESS, self._calculate_sensitive_data_risk)

    def log_event(self, event: AuditEvent):
        if event.risk_score is None: event.risk_score = self._calculate_risk_score(event)
        sanitized = self._sanitize_event(event)
        log_data = _json_safe(asdict(sanitized))
        log_data["timestamp"] = sanitized.timestamp.isoformat()
        if event.severity == AuditSeverity.CRITICAL: self.logger.critical(json.dumps(log_data, cls=DjangoJSONEncoder))
        elif event.severity == AuditSeverity.ERROR: self.logger.error(json.dumps(log_data, cls=DjangoJSONEncoder))
        elif event.severity == AuditSeverity.WARNING: self.logger.warning(json.dumps(log_data, cls=DjangoJSONEncoder))
        else: self.logger.info(json.dumps(log_data, cls=DjangoJSONEncoder))
        self._execute_event_handlers(sanitized)
        self._detect_anomalies(sanitized)

    def _sanitize_event(self, event: AuditEvent) -> AuditEvent:
        sanitized = AuditEvent(**asdict(event))
        if sanitized.old_value is not None: sanitized.old_value = self._mask_sensitive_payload(sanitized.old_value)
        if sanitized.new_value is not None: sanitized.new_value = self._mask_sensitive_payload(sanitized.new_value)
        if sanitized.field_name and sanitized.field_name.lower() in self.sensitive_fields:
            if sanitized.old_value: sanitized.old_value = "***MASKED***"
            if sanitized.new_value: sanitized.new_value = "***MASKED***"
        if sanitized.variables: sanitized.variables = self._mask_sensitive_variables(sanitized.variables)
        if sanitized.details: sanitized.details = self._mask_sensitive_details(sanitized.details)
        return sanitized

    def _mask_sensitive_variables(self, variables: dict) -> dict:
        masked = {}
        for k, v in variables.items():
            if k.lower() in self.sensitive_fields: masked[k] = "***MASKED***"
            elif isinstance(v, dict): masked[k] = self._mask_sensitive_variables(v)
            elif isinstance(v, list): masked[k] = [self._mask_sensitive_variables(i) if isinstance(i, dict) else i for i in v]
            else: masked[k] = v
        return masked

    def _mask_sensitive_details(self, details: dict) -> dict: return self._mask_sensitive_variables(details)
    def _mask_sensitive_payload(self, payload: any) -> any: return self._mask_sensitive_variables(payload) if isinstance(payload, (dict, list)) else payload

    def _calculate_risk_score(self, event: AuditEvent) -> int:
        if event.event_type in self._risk_calculators: return self._risk_calculators[event.event_type](event)
        score = {AuditSeverity.INFO: 10, AuditSeverity.WARNING: 30, AuditSeverity.ERROR: 60, AuditSeverity.CRITICAL: 90}.get(event.severity, 10)
        if event.event_type in [AuditEventType.LOGIN_FAILURE, AuditEventType.PERMISSION_DENIED, AuditEventType.SECURITY_VIOLATION]: score += 20
        if event.field_name and event.field_name.lower() in self.sensitive_fields: score += 15
        if event.operation_name and event.operation_name.lower() in self.high_risk_operations: score += 25
        return min(score, 100)

    def _calculate_login_failure_risk(self, event: AuditEvent) -> int: return 30
    def _calculate_permission_denied_risk(self, event: AuditEvent) -> int:
        score = 40
        if event.field_name and event.field_name.lower() in self.sensitive_fields: score += 20
        return score

    def _calculate_sensitive_data_risk(self, event: AuditEvent) -> int:
        score, f = 50, (event.field_name or "").lower()
        if any(s in f for s in ["password", "token", "secret"]): score += 30
        elif any(s in f for s in ["ssn", "credit_card", "bank"]): score += 25
        return score

    def register_risk_calculator(self, event_type: AuditEventType, calculator: callable): self._risk_calculators[event_type] = calculator
    def register_event_handler(self, event_type: AuditEventType, handler: callable):
        if event_type not in self._event_handlers: self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def _execute_event_handlers(self, event: AuditEvent):
        for h in self._event_handlers.get(event.event_type, []):
            try: h(event)
            except Exception: logger.error("Erreur dans le gestionnaire d'Ç¸vÇ¸nement")

    def _detect_anomalies(self, event: AuditEvent):
        if event.event_type == AuditEventType.LOGIN_FAILURE: pass
        elif event.event_type == AuditEventType.SENSITIVE_DATA_ACCESS: pass
        elif event.event_type == AuditEventType.SECURITY_VIOLATION: pass


audit_logger = AuditLogger()
