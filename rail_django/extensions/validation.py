"""
Input validation and security module for Django GraphQL Auto-Generation.

This module provides comprehensive input validation, sanitization,
and security measures to prevent common attacks.
"""

import html
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import urlparse

import graphene
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email
from django.db import models
from django.utils.html import strip_tags

# Import des nouvelles exceptions personnalisées
from ..core.exceptions import SecurityError
from ..core.exceptions import ValidationError as GraphQLValidationError

logger = logging.getLogger(__name__)


class InputSanitizer:
    """Classe pour nettoyer et sécuriser les entrées utilisateur."""

    # Patterns dangereux pour la détection d'injections SQL
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
        r"(--|#|/\*|\*/)",
        r"(\b(OR|AND)\s+\d+\s*=\s*\d+)",
        r"(\bUNION\s+SELECT\b)",
        r"(\b(SCRIPT|JAVASCRIPT|VBSCRIPT)\b)",
    ]

    # Patterns XSS
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"<iframe[^>]*>.*?</iframe>",
        r"<object[^>]*>.*?</object>",
        r"<embed[^>]*>.*?</embed>",
    ]

    # Caractères dangereux
    DANGEROUS_CHARS = ['<', '>', '"', "'", '&', '\x00', '\x08', '\x0b', '\x0c', '\x0e', '\x0f']

    @classmethod
    def sanitize_string(cls, value: str, allow_html: bool = False) -> str:
        """
        Nettoie une chaîne de caractères.

        Args:
            value: Valeur à nettoyer
            allow_html: Autoriser le HTML (par défaut False)

        Returns:
            Chaîne nettoyée

        Raises:
            SecurityError: Si une menace est détectée
        """
        if not isinstance(value, str):
            return str(value)

        # Détection d'injection SQL
        cls._detect_sql_injection(value)

        # Détection XSS
        cls._detect_xss(value)

        # Nettoyage de base
        cleaned = value.strip()

        # Suppression des caractères de contrôle dangereux
        for char in cls.DANGEROUS_CHARS:
            if char in cleaned:
                cleaned = cleaned.replace(char, '')

        # Gestion du HTML
        if not allow_html:
            cleaned = strip_tags(cleaned)
            cleaned = html.escape(cleaned)
        else:
            # Nettoyage HTML sélectif (garde les balises sûres)
            cleaned = cls._sanitize_html(cleaned)

        return cleaned

    @classmethod
    def _detect_sql_injection(cls, value: str):
        """Détecte les tentatives d'injection SQL."""
        value_upper = value.upper()

        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value_upper, re.IGNORECASE):
                logger.warning(f"Tentative d'injection SQL détectée: {value[:100]}")
                raise SecurityError(
                    "Contenu potentiellement dangereux détecté",
                    threat_type="sql_injection"
                )

    @classmethod
    def _detect_xss(cls, value: str):
        """Détecte les tentatives XSS."""
        for pattern in cls.XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"Tentative XSS détectée: {value[:100]}")
                raise SecurityError(
                    "Contenu potentiellement dangereux détecté",
                    threat_type="xss"
                )

    @classmethod
    def _sanitize_html(cls, value: str) -> str:
        """Nettoie le HTML en gardant les balises sûres."""
        # Liste des balises autorisées
        allowed_tags = ['p', 'br', 'strong', 'em', 'u', 'ol',
                        'ul', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']

        # Suppression des balises non autorisées
        # Cette implémentation est basique, pour la production utiliser bleach
        import re

        # Suppression des attributs dangereux
        value = re.sub(r'on\w+\s*=\s*["\'][^"\']*["\']', '', value, flags=re.IGNORECASE)
        value = re.sub(r'javascript:', '', value, flags=re.IGNORECASE)

        return value


class FieldValidator:
    """Validateur pour les champs spécifiques."""

    @staticmethod
    def validate_email_field(value: str) -> str:
        """
        Valide et nettoie un champ email.

        Args:
            value: Adresse email à valider

        Returns:
            Email validé et nettoyé

        Raises:
            GraphQLValidationError: Si l'email n'est pas valide
        """
        if not value:
            raise GraphQLValidationError("L'adresse email est requise", field="email")

        # Nettoyage de base
        cleaned_email = InputSanitizer.sanitize_string(value).lower().strip()

        # Validation du format
        try:
            validate_email(cleaned_email)
        except ValidationError as e:
            raise GraphQLValidationError(f"Format d'email invalide: {e}", field="email")

        return cleaned_email

    @staticmethod
    def validate_url_field(value: str) -> str:
        """
        Valide et nettoie un champ URL.

        Args:
            value: URL à valider

        Returns:
            URL validée et nettoyée

        Raises:
            ValidationError: Si l'URL n'est pas valide
        """
        if not value:
            return value

        # Nettoyage de base
        cleaned_url = InputSanitizer.sanitize_string(value).strip()

        # Validation du format
        try:
            validator = URLValidator()
            validator(value)

            # Vérification du protocole
            parsed = urlparse(value)
            if parsed.scheme not in ['http', 'https']:
                raise GraphQLValidationError(
                    "Seuls les protocoles HTTP et HTTPS sont autorisés", field="url")

            return value
        except ValidationError as e:
            raise GraphQLValidationError(f"Format d'URL invalide: {e}", field="url")

        # Vérification du protocole (seulement http/https)
        parsed = urlparse(cleaned_url)
        if parsed.scheme not in ['http', 'https']:
            raise ValidationError("Seuls les protocoles HTTP et HTTPS sont autorisés", "url")

        return cleaned_url

    @staticmethod
    def validate_integer_field(value: Any, min_value: int = None, max_value: int = None) -> int:
        """
        Valide un champ entier.

        Args:
            value: Valeur à valider
            min_value: Valeur minimale autorisée
            max_value: Valeur maximale autorisée

        Returns:
            Entier validé

        Raises:
            ValidationError: Si la valeur n'est pas valide
        """
        try:
            int_value = int(value)
        except (ValueError, TypeError):
            raise GraphQLValidationError("Valeur entière requise", field="integer")

        if min_value is not None and int_value < min_value:
            raise GraphQLValidationError(
                f"La valeur doit être supérieure ou égale à {min_value}", field="integer")

        if max_value is not None and int_value > max_value:
            raise GraphQLValidationError(
                f"La valeur doit être inférieure ou égale à {max_value}", field="integer")

        return int_value

    @staticmethod
    def validate_decimal_field(value: Any, max_digits: int = None, decimal_places: int = None) -> Decimal:
        """
        Valide un champ décimal.

        Args:
            value: Valeur à valider
            max_digits: Nombre maximum de chiffres
            decimal_places: Nombre de décimales

        Returns:
            Décimal validé

        Raises:
            ValidationError: Si la valeur n'est pas valide
        """
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise GraphQLValidationError("Valeur décimale requise", field="decimal")

        if max_digits is not None:
            # Vérification du nombre total de chiffres
            sign, digits, exponent = decimal_value.as_tuple()
            total_digits = len(digits)
            if total_digits > max_digits:
                raise GraphQLValidationError(
                    f"Maximum {max_digits} chiffres autorisés", field="decimal")

        if decimal_places is not None:
            # Vérification du nombre de décimales
            sign, digits, exponent = decimal_value.as_tuple()
            if exponent < -decimal_places:
                raise GraphQLValidationError(
                    f"Maximum {decimal_places} décimales autorisées", field="decimal")

        return decimal_value

    @staticmethod
    def validate_string_field(value: str, min_length: int = None, max_length: int = None,
                              pattern: str = None, allow_html: bool = False) -> str:
        """
        Valide un champ chaîne de caractères.

        Args:
            value: Valeur à valider
            min_length: Longueur minimale
            max_length: Longueur maximale
            pattern: Pattern regex à respecter
            allow_html: Autoriser le HTML

        Returns:
            Chaîne validée et nettoyée

        Raises:
            ValidationError: Si la valeur n'est pas valide
        """
        if value is None:
            value = ""

        # Nettoyage de sécurité
        cleaned_value = InputSanitizer.sanitize_string(str(value), allow_html=allow_html)

        # Validation de la longueur
        if min_length is not None and len(cleaned_value) < min_length:
            raise GraphQLValidationError(
                f"Longueur minimale: {min_length} caractères", field="string")

        if max_length is not None and len(cleaned_value) > max_length:
            raise GraphQLValidationError(
                f"Longueur maximale: {max_length} caractères", field="string")

        # Validation du pattern
        if pattern and not re.match(pattern, cleaned_value):
            raise GraphQLValidationError("Format invalide", field="string")

        return cleaned_value


class InputValidator:
    """Validateur principal pour les entrées GraphQL."""

    def __init__(self):
        self.field_validators: Dict[str, Callable] = {}
        self.model_validators: Dict[str, List[Callable]] = {}

    def register_field_validator(self, field_name: str, validator: Callable):
        """
        Enregistre un validateur pour un champ spécifique.

        Args:
            field_name: Nom du champ
            validator: Fonction de validation
        """
        self.field_validators[field_name] = validator
        logger.info(f"Validateur de champ enregistré: {field_name}")

    def register_model_validator(self, model_name: str, validator: Callable):
        """
        Enregistre un validateur pour un modèle.

        Args:
            model_name: Nom du modèle
            validator: Fonction de validation
        """
        if model_name not in self.model_validators:
            self.model_validators[model_name] = []

        self.model_validators[model_name].append(validator)
        logger.info(f"Validateur de modèle enregistré: {model_name}")

    def validate_input(self, model_name: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valide et nettoie les données d'entrée.

        Args:
            model_name: Nom du modèle
            input_data: Données à valider

        Returns:
            Données validées et nettoyées

        Raises:
            ValidationError: Si la validation échoue
        """
        validated_data = {}

        for field_name, value in input_data.items():
            # Validation par champ spécifique
            if field_name in self.field_validators:
                try:
                    validated_data[field_name] = self.field_validators[field_name](value)
                except Exception as e:
                    raise GraphQLValidationError(
                        f"Erreur de validation pour {field_name}: {e}", field=field_name)
            else:
                # Validation générique basée sur le type
                validated_data[field_name] = self._validate_generic_field(field_name, value)

        # Validation au niveau du modèle
        for validator in self.model_validators.get(model_name, []):
            try:
                validator(validated_data)
            except Exception as e:
                raise GraphQLValidationError(f"Erreur de validation du modèle {model_name}: {e}")

        return validated_data

    def _validate_generic_field(self, field_name: str, value: Any) -> Any:
        """Validation générique basée sur le type de la valeur."""
        if value is None:
            return value

        if isinstance(value, str):
            # Détection automatique du type de champ
            if 'email' in field_name.lower():
                return FieldValidator.validate_email_field(value)
            elif 'url' in field_name.lower() or 'link' in field_name.lower():
                return FieldValidator.validate_url_field(value)
            else:
                return FieldValidator.validate_string_field(value, max_length=1000)

        elif isinstance(value, int):
            return FieldValidator.validate_integer_field(value)

        elif isinstance(value, (float, Decimal)):
            return FieldValidator.validate_decimal_field(value)

        else:
            # Pour les autres types, nettoyage de base
            return value


# Instance globale du validateur
input_validator = InputValidator()


def validate_input(model_name: str = None):
    """
    Décorateur pour valider les entrées des mutations GraphQL.

    Args:
        model_name: Nom du modèle (optionnel)
    """
    def decorator(func):
        def wrapper(self, info, **kwargs):
            # Extraction du nom du modèle si non fourni
            if model_name is None:
                model_class = getattr(self, 'model_class', None)
                if model_class:
                    current_model_name = model_class._meta.label_lower
                else:
                    current_model_name = "unknown"
            else:
                current_model_name = model_name

            # Validation des données d'entrée
            try:
                # Recherche des arguments d'entrée (input, data, etc.)
                input_data = {}
                for key, value in kwargs.items():
                    if key in ['input', 'data'] or key.endswith('_data'):
                        if hasattr(value, '__dict__'):
                            input_data.update(value.__dict__)
                        elif isinstance(value, dict):
                            input_data.update(value)

                if input_data:
                    validated_data = input_validator.validate_input(current_model_name, input_data)

                    # Mise à jour des kwargs avec les données validées
                    for key, value in kwargs.items():
                        if key in ['input', 'data'] or key.endswith('_data'):
                            if hasattr(value, '__dict__'):
                                for field, validated_value in validated_data.items():
                                    setattr(value, field, validated_value)
                            elif isinstance(value, dict):
                                kwargs[key].update(validated_data)

            except GraphQLValidationError as e:
                logger.warning(f"Erreur de validation: {e.message}")
                raise GraphQLValidationError(e.message)
            except SecurityError as e:
                logger.error(f"Menace de sécurité détectée: {e.message}")
                raise SecurityError(e.message)

            return func(self, info, **kwargs)
        return wrapper
    return decorator


def setup_default_validators():
    """Configure les validateurs par défaut."""

    # Validateurs pour les champs communs
    input_validator.register_field_validator('email', FieldValidator.validate_email_field)
    input_validator.register_field_validator('url', FieldValidator.validate_url_field)
    input_validator.register_field_validator('website', FieldValidator.validate_url_field)

    # Validateur pour les mots de passe
    def validate_password(value: str) -> str:
        """Valide un mot de passe."""
        if len(value) < 8:
            raise GraphQLValidationError(
                "Le mot de passe doit contenir au moins 8 caractères", field="password")

        if not re.search(r'[A-Z]', value):
            raise GraphQLValidationError(
                "Le mot de passe doit contenir au moins une majuscule", field="password")

        if not re.search(r'[a-z]', value):
            raise GraphQLValidationError(
                "Le mot de passe doit contenir au moins une minuscule", field="password")

        if not re.search(r'\d', value):
            raise GraphQLValidationError(
                "Le mot de passe doit contenir au moins un chiffre", field="password")

        return value

    input_validator.register_field_validator('password', validate_password)

    logger.info("Validateurs par défaut configurés")


# Configuration automatique des validateurs par défaut
setup_default_validators()


class ValidationInfo(graphene.ObjectType):
    """Informations sur la validation d'un champ."""

    field_name = graphene.String(description="Nom du champ")
    is_valid = graphene.Boolean(description="Le champ est-il valide")
    error_message = graphene.String(description="Message d'erreur")
    sanitized_value = graphene.String(description="Valeur nettoyée")


class ValidationQuery(graphene.ObjectType):
    """Queries pour tester la validation."""

    validate_field = graphene.Field(
        ValidationInfo,
        field_name=graphene.String(required=True),
        value=graphene.String(required=True),
        description="Valide un champ spécifique"
    )

    def resolve_validate_field(self, info, field_name: str, value: str):
        """Valide un champ et retourne les informations."""
        try:
            if field_name in input_validator.field_validators:
                sanitized = input_validator.field_validators[field_name](value)
            else:
                sanitized = input_validator._validate_generic_field(field_name, value)

            return ValidationInfo(
                field_name=field_name,
                is_valid=True,
                error_message=None,
                sanitized_value=str(sanitized)
            )

        except (GraphQLValidationError, SecurityError) as e:
            return ValidationInfo(
                field_name=field_name,
                is_valid=False,
                error_message=str(e),
                sanitized_value=None
            )
