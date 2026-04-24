"""
Tests pour la protection PII automatique dans le dispatcher de webhooks.

Ce module valide que les champs contenant des données sensibles (mots de
passe, tokens, SSN, etc.) sont automatiquement masqués dans les payloads
de webhooks, même sans configuration explicite de ``redact_fields``.
"""

import re

import pytest

from rail_django.webhooks.dispatcher import _PII_FIELD_PATTERNS


@pytest.mark.unit
class TestPIIFieldPatterns:
    """Tests pour le pattern regex _PII_FIELD_PATTERNS."""

    @pytest.mark.parametrize(
        "field_name",
        [
            "password",
            "user_password",
            "password_hash",
            "passwd",
            "pwd",
            "secret",
            "signing_secret",
            "api_key",
            "private_key",
            "token",
            "access_token",
            "refresh_token",
            "auth_token",
            "ssn",
            "social_security",
            "national_id",
            "credit_card",
            "card_number",
            "cvv",
            "cvc",
            "pin",
            "security_code",
            "otp",
            "two_factor",
            "mfa_secret",
        ],
    )
    def test_pii_field_detected(self, field_name):
        """Les champs sensibles doivent être détectés par le pattern."""
        assert _PII_FIELD_PATTERNS.search(field_name), (
            f"Le champ '{field_name}' devrait être détecté comme PII"
        )

    @pytest.mark.parametrize(
        "field_name",
        [
            "name",
            "email",
            "username",
            "first_name",
            "last_name",
            "description",
            "title",
            "created_at",
            "updated_at",
            "is_active",
            "amount",
            "quantity",
            "status",
            "category",
        ],
    )
    def test_non_pii_field_not_detected(self, field_name):
        """Les champs non-sensibles ne doivent pas être détectés."""
        assert not _PII_FIELD_PATTERNS.search(field_name), (
            f"Le champ '{field_name}' ne devrait pas être détecté comme PII"
        )

    def test_case_insensitive_matching(self):
        """Le pattern doit être insensible à la casse pour les noms snake_case."""
        assert _PII_FIELD_PATTERNS.search("Password")
        assert _PII_FIELD_PATTERNS.search("API_KEY")
        assert _PII_FIELD_PATTERNS.search("access_token")
        # camelCase ne correspond pas car Django utilise snake_case
        assert not _PII_FIELD_PATTERNS.search("AccessToken")
